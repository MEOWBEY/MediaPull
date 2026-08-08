<script lang="ts">
	import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
	import Waypoints from '@lucide/svelte/icons/waypoints';
	import { onDestroy, onMount, tick, untrack } from 'svelte';
	import { toast } from 'svelte-sonner';

	import QualityMenu from '$lib/components/QualityMenu.svelte';
	import SubtitlePanel from '$lib/components/SubtitlePanel.svelte';
	import { Button } from '$lib/components/ui/button';
	import { resolveApiUrl } from '$lib/config';
	import { safeFilename } from '$lib/export';
	import { isAudioType, mediaKindLabel, qualityLabel } from '$lib/format';
	import { i18n } from '$lib/i18n/index.svelte';
	import { appStore } from '$lib/stores/app-state.svelte';
	import { SubtitleResolver } from '$lib/subtitle-resolver.svelte';
	import type { FormatGroup, SubtitleTrack, SubtitleTrackResult, VideoFormat } from '$lib/types';

	const { t } = i18n;

	/** Imperative handle the parent card uses to drive subtitles from its own
	 *  toolbar's Subtitles button, instead of a `bind:this` ref which doesn't
	 *  fit cleanly inside a keyed `{#each}`. */
	export interface VideoPlayerHandle {
		requestSubtitles: () => Promise<void>;
		openSubtitlePanel: () => void;
		/** Resolves true only when the track actually yielded usable cues. */
		useExistingTrack: (track: SubtitleTrack) => Promise<boolean>;
		cancelSubtitles: () => void;
		/** Switch the active format-group tab. Lets the parent render the tab
		 *  strip itself (e.g. as a separate column in row layout) while switching
		 *  still runs through this player's single instance. */
		switchGroup: (index: number) => void;
	}

	/** Pushed to the parent whenever subtitle state changes, so the card
	 *  header can reactively show the CC button / spinner / percentage. */
	export interface SubtitleState {
		hasTrack: boolean;
		isRunning: boolean;
		progress: number;
		/** Human-readable current pipeline stage, for a tooltip next to the
		 *  percentage ("Acquiring audio…", "Transcribing... (3 of 8 done)"). */
		stepLabel: string;
		/** True while an existing source caption is being fetched/parsed --
		 *  distinct from `isRunning` (the Groq job) since it never has a
		 *  meaningful progress percentage. */
		isResolvingExisting: boolean;
	}

	let {
		poster = '',
		formatGroups = [],
		useProxy = true,
		onToggleProxy,
		rowLayout = false,
		showFormatTabs = false,
		title = '',
		webpageUrl = '',
		duration = 0,
		initialSubtitleTrack = null,
		onReady,
		onSubtitleState,
		onActiveGroupChange,
		onSubtitleTrackChange
	}: {
		poster?: string;
		formatGroups?: FormatGroup[];
		useProxy?: boolean;
		/** Lets the error overlay offer "switch proxy mode" as an actual button
		 *  instead of just telling the user to go find the toggle elsewhere. */
		onToggleProxy?: () => void;
		/** Row-layout card: the player sits in a narrow start-side column, so the
		 *  format-kind tabs stack vertically (one per line) instead of a horizontal
		 *  strip that would wrap awkwardly in the tight column. */
		rowLayout?: boolean;
		/** Force the format-kind tab strip even with a single group (local
		 *  files) so local cards carry the same kind badge as online tabs. */
		showFormatTabs?: boolean;
		/** Video title -- used to name the downloaded subtitle (.srt) file. */
		title?: string;
		webpageUrl?: string;
		/** Video duration (seconds) as extraction reported it -- forwarded with
		 *  the transcription request so the server can compute real acquisition
		 *  progress. 0/undefined is fine (progress degrades gracefully). */
		duration?: number;
		/** Restores a previously generated/reused track (see `onSubtitleTrackChange`)
		 *  so a page refresh doesn't lose it or force re-transcribing. */
		initialSubtitleTrack?: SubtitleTrackResult | null;
		onReady?: (handle: VideoPlayerHandle) => void;
		onSubtitleState?: (state: SubtitleState) => void;
		onActiveGroupChange?: (index: number) => void;
		/** Fired whenever the resolved subtitle track changes, so the parent can
		 *  persist it alongside the card (survives refresh, removed with the video). */
		onSubtitleTrackChange?: (track: SubtitleTrackResult | null) => void;
	} = $props();

	// Which format-group "tab" is active (progressive MP4 / HLS / a separate
	// audio-only stream, ...) -- several tabs share this one player instance,
	// since they're all the same source and one subtitle track covers all of them.
	let activeGroupIndex = $state(0);
	const activeGroup = $derived(formatGroups[activeGroupIndex] ?? formatGroups[0]);
	const qualities = $derived(activeGroup?.qualities ?? []);

	// Audio-only media gets a compact native <audio> player (no video frame),
	// instead of the aspect-video skin used for visual formats.
	const isAudio = $derived(isAudioType(activeGroup?.type ?? ''));

	const { preferences } = appStore;

	// Both <video> and <hls-video> expose the media subset we drive (currentTime,
	// paused, play, load) but aren't the same DOM type — narrow to that.
	type MediaEl = HTMLElement &
		Pick<
			HTMLMediaElement,
			'currentTime' | 'paused' | 'play' | 'load' | 'muted' | 'volume' | 'duration'
		>;
	type HlsEl = MediaEl & { config?: Record<string, unknown> };
	// The <video-player>/<audio-player> host element -- exposes the player's
	// reactive store (`.store.state`), which is what its own captions button
	// drives via `toggleSubtitles()`. Typed loosely since it's a third-party
	// custom element with no published TS types for this property.
	type PlayerRootEl = HTMLElement & {
		store?: { state: { toggleSubtitles?: (forceShow?: boolean) => boolean } };
	};

	// Passed through to hls.js. The engine already caps the level to the player
	// size and on FPS drops; these trim memory, recover faster on flaky
	// connections, and make seeks settle quicker without changing adaptive bitrate.
	const HLS_CONFIG = {
		maxBufferLength: 30,
		maxMaxBufferLength: 60,
		maxBufferHole: 0.5,
		nudgeMaxRetry: 6,
		fragLoadingMaxRetry: 6,
		manifestLoadingMaxRetry: 4
	};

	// $state (not a plain variable) so effects correctly re-run when the
	// element itself is swapped out -- e.g. switching format-group tabs
	// remounts it, and the "now playing" / caption-mode effects below need to
	// pick up the new element rather than keep driving the torn-down one.
	let videoEl = $state<MediaEl | null>(null);
	// The <video-player>/<audio-player> host -- see `PlayerRootEl` above.
	let playerRootEl: PlayerRootEl | null = $state(null);
	let ready = $state(false);
	let hasError = $state(false);
	let activeIndex = $state(0);
	// Mirrors the skin's own control-bar visibility so the quality button fades
	// in and out together with the controls.
	let controlsVisible = $state(true);

	// ----- Auto-subtitles (speech-to-text, no translation, or a caption the
	// source already provides) -- see subtitle-resolver.svelte.ts. -----------
	const subtitles = new SubtitleResolver();

	// Reactive (not mount-only) restore: a parent card hands a resolved track
	// in via prop WHILE the player is already mounted -- a local file's
	// generation finishes server-side, and LocalFileCard only then mirrors the
	// result into initialSubtitleTrack. The $effect re-runs whenever the prop
	// changes, so that late hand-off is picked up; the tracked read is just
	// the prop (wrap restore's own reads in untrack so its internal writes
	// can't re-trigger the effect), and `restore` is idempotent for a prop
	// that hasn't changed. Online cards never set this prop -- they generate
	// through this resolver's own pipeline, so nothing changes for them.
	$effect(() => {
		if (!initialSubtitleTrack) {
			return;
		}

		untrack(() => subtitles.restore(initialSubtitleTrack));
	});

	let subtitlePanelOpen = $state(false);
	let playerCurrentTime = $state(0);

	const activeSubtitleTrack = $derived(subtitles.track);

	// Report resolved-track changes up so the parent can persist them
	// alongside the card (survives refresh; removed automatically when the
	// video itself is removed, since it lives on the same object). Tracked
	// against the last-reported value (not just "did it change from null") so
	// restoring `initialSubtitleTrack` on mount doesn't immediately re-report
	// the exact value the parent just handed in.
	let lastReportedTrack: SubtitleTrackResult | null = untrack(() => initialSubtitleTrack ?? null);

	$effect(() => {
		if (activeSubtitleTrack === lastReportedTrack) {
			return;
		}

		lastReportedTrack = activeSubtitleTrack;
		onSubtitleTrackChange?.(activeSubtitleTrack);
	});

	// Keep the parent card's header controls in sync (CC button visibility,
	// spinner + percentage while a job runs).
	$effect(() => {
		onSubtitleState?.({
			hasTrack: Boolean(activeSubtitleTrack),
			isRunning: subtitles.isRunning,
			progress: subtitles.progress,
			stepLabel: subtitles.stepLabel,
			isResolvingExisting: subtitles.resolvingExisting
		});
	});

	// Drive the subtitle panel's "now playing" position. Runs while a track
	// exists and the panel is open.
	$effect(() => {
		const needTime = Boolean(activeSubtitleTrack) && Boolean(videoEl) && subtitlePanelOpen;

		if (!needTime || !videoEl) {
			return;
		}

		const el = videoEl;
		const onTimeUpdate = () => {
			playerCurrentTime = el.currentTime;
		};

		el.addEventListener('timeupdate', onTimeUpdate);
		onTimeUpdate();

		return () => el.removeEventListener('timeupdate', onTimeUpdate);
	});

	// Browsers don't reliably honor a <track default> added dynamically after
	// the media element already exists (our case: the track only appears once
	// transcription/existing-caption lookup resolves, well after mount). Just
	// poking `textTrack.mode = 'showing'` isn't enough either: the packaged
	// skin (@videojs/html) has its own captions button/state that only
	// auto-shows native tracks of kind "chapters"/"metadata", not
	// "subtitles"/"captions" -- setting the mode directly leaves the skin's
	// own captions UI unaware, so its (invisible, never-toggled) internal
	// state fights the browser's rendering. Driving it through the skin's own
	// `toggleSubtitles()` (the exact same call its CC button makes) keeps the
	// native cue rendering AND the CC button's own "on" state in sync.
	$effect(() => {
		if (!activeSubtitleTrack?.vttUrl || !videoEl) {
			return;
		}

		const el = videoEl as unknown as HTMLMediaElement;
		const tracks = el.textTracks;

		if (!tracks) {
			return;
		}

		const apply = () => {
			(playerRootEl as PlayerRootEl | null)?.store?.state.toggleSubtitles?.(true);
		};

		apply();
		tracks.addEventListener('addtrack', apply);

		return () => tracks.removeEventListener('addtrack', apply);
	});

	async function generateSubtitles() {
		// Every format-group's qualities, not just the active tab's -- a
		// dedicated audio-only stream may live in a different tab than the one
		// currently playing, and the backend already knows how to pick the
		// best audio-bearing source out of a mixed bag.
		await subtitles.generate({
			webpageUrl,
			durationSeconds: duration || undefined,
			qualities: formatGroups.flatMap((g) => g.qualities)
		});
	}

	function cancelSubtitles() {
		subtitles.cancel();
	}

	// Handed to the parent once, via onReady.
	onMount(() => {
		onReady?.({
			requestSubtitles: () => generateSubtitles(),
			openSubtitlePanel: () => (subtitlePanelOpen = true),
			useExistingTrack: (track: SubtitleTrack) => subtitles.useExisting(track),
			cancelSubtitles,
			switchGroup: (index: number) => void switchGroup(index)
		});
	});

	// Removing this card (unmounts VideoPlayer) or navigating away shouldn't
	// leave an in-flight Groq job running server-side with nobody watching
	// it -- cancel() aborts locally and best-effort tells the server to free
	// the job's slot.
	onDestroy(() => {
		subtitles.cancel();
	});

	// A full page refresh/close kills the JS runtime before onDestroy's normal
	// fetch could reliably complete, so this needs its own `keepalive` request
	// (survives page teardown, unlike a plain fetch) rather than reusing
	// cancel()'s fire-and-forget call. There's no central place that tracks
	// every active player/resolver instance (VideoExtractList only renders
	// VideoCard per item, with no ref collection -- see its onReady handling),
	// so this is scoped to this player's own job instead of a new global
	// registry.
	if (typeof window !== 'undefined') {
		const onBeforeUnload = () => {
			const jobId = subtitles.currentJobId;

			if (!jobId) {
				return;
			}

			fetch(resolveApiUrl(`/transcribe/${jobId}`), { method: 'DELETE', keepalive: true }).catch(
				() => {}
			);
		};

		window.addEventListener('beforeunload', onBeforeUnload);
		onDestroy(() => window.removeEventListener('beforeunload', onBeforeUnload));
	}

	function seekTo(time: number) {
		if (videoEl) {
			videoEl.currentTime = time;
		}
	}

	function downloadSrt() {
		const url = activeSubtitleTrack?.srtUrl;

		if (!url) {
			return;
		}

		try {
			const link = document.createElement('a');

			link.href = url;
			link.download = `${safeFilename(title, 'subtitles')}.srt`;
			link.click();
		} catch {
			toast.error(t('toast.downloadFailed'));
		}
	}

	// Drop sources with no playable URL, then collapse duplicate qualities
	// (same resolution + extension) that some extractors return more than once.
	const usable = $derived.by(() => {
		const filtered = (qualities ?? []).filter((q) => q?.proxiedVideoUrl || q?.sourceVideoUrl);
		const seen: Record<string, true> = {};
		const out: Partial<VideoFormat>[] = [];

		for (const q of filtered) {
			const key = `${q.resolution ?? 0}-${(q.ext ?? '').toLowerCase()}-${q.proxiedVideoUrl || q.sourceVideoUrl}`;

			if (seen[key]) {
				continue;
			}
			seen[key] = true;
			out.push(q);
		}

		return out;
	});

	function urlFor(q: Partial<VideoFormat> | undefined): string {
		const proxied = q?.proxiedVideoUrl ?? '';
		const source = q?.sourceVideoUrl ?? '';

		return useProxy ? proxied || source : source || proxied;
	}

	function isHls(src: string): boolean {
		return src.includes('.m3u8');
	}

	const activeSrc = $derived(urlFor(usable[activeIndex]));
	// Our proxy adds `Access-Control-Allow-Origin: *`, so CORS mode is safe there.
	// Raw source URLs usually send no CORS headers — forcing crossorigin on them
	// makes the browser reject the media ("MEDIA_ELEMENT_ERROR: Format error").
	// (Backend route is `/proxy-video`, no `/api` prefix -- see proxy-url.ts.)
	const usingProxy = $derived(activeSrc.includes('/proxy-video'));
	// One unified menu for every format (mp4 / mp3 / avi / hls / …): switch by
	// swapping the source URL. Shown whenever the extractor gave more than one.
	const showQualityMenu = $derived(usable.length > 1);

	// Shared by switchQuality/switchGroup: capture the live runtime state
	// before `mutate()` swaps activeIndex/activeGroupIndex (and therefore the
	// rendered element -- possibly even crossing the audio/video skin
	// boundary), then reapply it to whichever element ends up mounted. Doing
	// the capture synchronously, before the state mutation, is what makes this
	// work: an `$effect` reacting to the change would only see the *new*
	// element, since Svelte re-renders before effects flush.
	// Serializes switches: without this, rapidly switching tab A -> B -> A
	// lets the calls race (the B->A capture can read B's element before its
	// own resume from A->B settled, e.g. `.paused` still true because `play()`
	// hadn't actually started yet), leaving the final element stuck paused.
	let switching = $state(false);

	async function resumePlaybackAcross(mutate: () => void): Promise<boolean> {
		if (switching) {
			return false;
		}
		switching = true;

		try {
			const prevEl = videoEl;
			const resumeTime = prevEl?.currentTime ?? 0;
			const wasPlaying = prevEl ? !prevEl.paused : false;
			const wasMuted = prevEl?.muted ?? preferences.enableVideoMute;
			const prevVolume = prevEl?.volume ?? 1;

			mutate();

			// Tears down the old element and mounts the new one (same element only
			// when just the `src` changes), so wait for that to bind before driving it.
			await tick();
			const el = videoEl;

			if (!el) {
				return true;
			}

			// Mute/volume can be applied immediately (no metadata needed), so the user's
			// sound choice survives the swap regardless of play state.
			el.muted = wasMuted;
			el.volume = prevVolume;

			// A native <audio> only picks up a new src after an explicit load();
			// <hls-video> (used for every non-audio source, HLS or not -- see
			// `mediaEl` above) reloads itself whenever its src/type attributes
			// change, so don't double-load it.
			if (isAudio) {
				try {
					el.load();
				} catch {
					/* element may not be ready; the code below still recovers */
				}
			}

			// Seek and play immediately rather than waiting for a `loadedmetadata`
			// event: per the media element spec, setting `currentTime`/calling
			// `play()` before metadata has loaded is well-defined and queued
			// internally by the browser. Waiting on the event would be unreliable
			// (the `hls-video` custom element doesn't reliably forward it) and,
			// worse, would run `play()` from inside an async gap or a `setTimeout`
			// fallback -- detached from the click's user-activation context, which
			// some browsers' autoplay policy silently rejects. Calling `play()`
			// straight away keeps it in the same call chain as the user's click.
			if (resumeTime > 0) {
				el.currentTime = resumeTime;
			}

			// Only force the new source to load when we were already playing — never
			// preload after a paused switch (keeps "no load before play" intact).
			// Awaiting it (rather than firing and forgetting) means `.paused` is
			// settled by the time the NEXT switch reads it.
			if (wasPlaying) {
				try {
					await el.play();
				} catch {
					/* autoplay blocked or aborted by a subsequent switch -- stays paused */
				}
			}

			return true;
		} finally {
			switching = false;
		}
	}

	async function switchQuality(index: number) {
		if (index === activeIndex) {
			return;
		}

		await resumePlaybackAcross(() => {
			activeIndex = index;
		});
	}

	async function switchGroup(index: number) {
		if (index === activeGroupIndex) {
			return;
		}

		const switched = await resumePlaybackAcross(() => {
			activeGroupIndex = index;
			activeIndex = 0;
		});

		// Only tell the parent (which drives the quality rail below the card)
		// once the switch actually ran -- a switch dropped by the `switching`
		// lock must not report an index the player didn't actually land on.
		if (switched) {
			onActiveGroupChange?.(index);
		}
	}

	function bindVideo(node: MediaEl) {
		videoEl = node;

		return {
			destroy() {
				if (videoEl === node) {
					videoEl = null;
				}
			}
		};
	}

	// Captures the <video-player>/<audio-player> host so the caption effect
	// can reach its store's `toggleSubtitles()` -- see `PlayerRootEl` above.
	function bindPlayerRoot(node: PlayerRootEl) {
		playerRootEl = node;

		return {
			destroy() {
				if (playerRootEl === node) {
					playerRootEl = null;
				}
			}
		};
	}

	// hls.js reads `config` when it builds the engine, so set it before the element
	// resolves its `src`. Setting the property (not an attribute) is required.
	function bindHls(node: MediaEl) {
		(node as HlsEl).config = { ...(node as HlsEl).config, ...HLS_CONFIG };

		return bindVideo(node);
	}

	// Follow the skin's control-bar visibility. The skin is an open-shadow web
	// component that toggles `data-visible` on its `.media-controls` element; mirror
	// that onto `controlsVisible` so our slotted quality button tracks it exactly.
	//
	// Two touch problems this handles, both rooted in the packaged skin's
	// hardcoded behaviour:
	//
	// 1. Tap should only ever REVEAL the bar, never hide it -- hiding is the job
	//    of the idle timer alone. The skin instead treats a tap as a *toggle*
	//    (`toggleControls`: visible -> hide, hidden -> show), so tapping a video
	//    whose bar is already up hides it -- producing the jarring up/down/up
	//    dance as the user taps around. We can't override the toggle (the skin's
	//    state object is frozen), so we neutralise the unwanted half at the DOM
	//    level: whenever the bar is hidden *right after a tap* (within
	//    TAP_HIDE_GUARD_MS), that's the toggle firing, not the idle timer (which
	//    only trips seconds after the last activity), so we immediately re-show
	//    it. Doing that from inside the MutationObserver callback (a microtask)
	//    lands before the browser paints, so the bar never visibly blinks.
	//    A separate backstop covers the opposite miss -- a tap on a hidden bar
	//    that the skin fails to open (stale active-state) -- by force-opening if
	//    the bar is still hidden once the skin has finished its own toggle.
	//
	// 2. Auto-hide too fast: the library hides controls a fixed 2s after the last
	//    activity (hardcoded IDLE_DELAY in @videojs/core, not configurable). On
	//    touch a single tap is the only activity, so the bar vanished 2s after
	//    showing -- too fast to read or hit a button. While the bar is visible
	//    and playing, poke the library's own activity path (a synthetic
	//    pointermove, exactly what a mouse wiggle sends) a couple of times to
	//    stretch the visible window to ~5s, the conventional mobile duration.
	const TOUCH_KEEPALIVE_MS = 1500;
	const TOUCH_KEEPALIVE_POKES = 2;
	// A hide landing within this window after a tap is the skin's tap-toggle, not
	// the idle timer, so it gets reversed. Must comfortably exceed the skin's
	// 200ms double-tap window (see @videojs/core gesture/tap.js), which is how
	// long the single-tap `toggleControls` action is deferred before it runs.
	const TAP_HIDE_GUARD_MS = 350;
	// Backstop for a tap on a hidden bar the skin never opened: re-check once the
	// skin's own (double-tap-window-deferred) toggle has had time to run.
	const TOUCH_REVEAL_CHECK_MS = 280;

	function bindSkin(node: HTMLElement) {
		let observer: MutationObserver | null = null;
		let raf = 0;
		let keepAliveTimer: ReturnType<typeof setTimeout> | null = null;
		let revealTimer: ReturnType<typeof setTimeout> | null = null;
		let visibleAtTouchStart = false;
		// When the last tap ended -- lets the observer tell a tap-toggle hide
		// (reverse it) from an idle-timer hide (allow it). See problem 1 above.
		let lastTapEndAt = 0;
		const controlsEl = () => node.shadowRoot?.querySelector('.media-controls');
		const isControlsVisible = () => !!controlsEl()?.hasAttribute('data-visible');
		const pokeActivity = () =>
			videoEl?.dispatchEvent(new PointerEvent('pointermove', { bubbles: true, composed: true }));

		const attach = () => {
			const controls = controlsEl();

			if (!controls) {
				raf = requestAnimationFrame(attach);

				return;
			}

			const sync = () => {
				const visible = controls.hasAttribute('data-visible');

				// A hide right after a tap is the skin's tap-toggle, not the idle
				// timer -- undo it so taps only ever reveal the bar. Re-showing here
				// (a microtask) beats the next paint, so the bar doesn't blink.
				if (controlsVisible && !visible && Date.now() - lastTapEndAt < TAP_HIDE_GUARD_MS) {
					pokeActivity();

					return;
				}

				controlsVisible = visible;
			};

			sync();
			observer = new MutationObserver(sync);
			observer.observe(controls, { attributes: true, attributeFilter: ['data-visible'] });
		};

		const poke = (remaining: number) => {
			keepAliveTimer = setTimeout(() => {
				keepAliveTimer = null;

				if (remaining <= 0 || !videoEl || videoEl.paused) {
					return;
				}

				if (!isControlsVisible()) {
					return;
				}

				pokeActivity();
				poke(remaining - 1);
			}, TOUCH_KEEPALIVE_MS);
		};

		const onTouchStart = () => {
			visibleAtTouchStart = isControlsVisible();
		};

		const onTouchEnd = () => {
			lastTapEndAt = Date.now();

			if (keepAliveTimer) {
				clearTimeout(keepAliveTimer);
			}
			if (revealTimer) {
				clearTimeout(revealTimer);
			}

			// A tap that began while the bar was hidden must reveal it. If the
			// skin's toggle left it hidden anyway (stale active-state), force it
			// open so the user never has to tap twice.
			if (!visibleAtTouchStart) {
				revealTimer = setTimeout(() => {
					revealTimer = null;
					if (!isControlsVisible()) {
						pokeActivity();
					}
				}, TOUCH_REVEAL_CHECK_MS);
			}

			poke(TOUCH_KEEPALIVE_POKES);
		};

		attach();
		node.addEventListener('touchstart', onTouchStart, { passive: true });
		node.addEventListener('touchend', onTouchEnd, { passive: true });

		return {
			destroy() {
				cancelAnimationFrame(raf);
				observer?.disconnect();
				node.removeEventListener('touchstart', onTouchStart);
				node.removeEventListener('touchend', onTouchEnd);

				if (keepAliveTimer) {
					clearTimeout(keepAliveTimer);
				}
				if (revealTimer) {
					clearTimeout(revealTimer);
				}
			}
		};
	}

	onMount(() => {
		if (!usable.length) {
			hasError = true;

			return;
		}

		let cancelled = false;

		// v10 custom elements are browser-only — load them after mount (SSR-safe).
		// Both skins are loaded regardless of the initial tab: switching
		// format-group tabs can flip between the audio and video skin after
		// mount, so whichever one is needed first must already be registered.
		(async () => {
			await Promise.all([
				import('@videojs/html/audio/minimal-skin'),
				import('@videojs/html/video/minimal-skin')
			]);
			await import('@videojs/html/media/hls-video');
			await import('@videojs/html/global.css');
			if (!cancelled) {
				ready = true;
			}
		})().catch(() => {
			if (!cancelled) {
				hasError = true;
			}
		});

		return () => {
			cancelled = true;
		};
	});
</script>

<!-- Shared media element. No {#key} on purpose: keying on the src would tear down
     and rebuild the element on every quality switch, severing the skin's controller
     binding (play/pause/mute stop working). We keep the same element and only change
     its `src`; switchQuality() reloads + restores state in place.

     For the video (non-audio) case we always mount <hls-video>, even for a
     plain progressive MP4 -- never a plain <video>. Reason: @videojs/html's
     <video-player> only discovers a bare <video>'s media target once, via a
     one-time fallback query run at mount; a *custom* element like <hls-video>
     re-registers itself with the player on every (re)connect instead. Since
     switchGroup() can flip between HLS and progressive formats, swapping
     between <hls-video> and a plain <video> tag left the player's control
     store pointing at a torn-down element after switching HLS -> MP4 --
     fullscreen/other buttons silently stopped working. Mounting <hls-video>
     unconditionally means only one custom element type ever exists for video,
     so it's always properly (re)registered. `type` is passed explicitly
     (rather than left to the element's own URL-extension guess, which
     assumes anything not ending in ".mp4" is HLS -- wrong for our proxied
     URLs/other containers) so it only spins up the hls.js engine for actual
     HLS sources; everything else runs through its plain native-<video>
     delegate, identical to what a bare <video> tag would do. -->
{#snippet mediaEl()}
	{#if isAudio}
		<audio
			use:bindVideo
			src={activeSrc}
			crossorigin={usingProxy ? 'anonymous' : undefined}
			muted={preferences.enableVideoMute}
			preload={preferences.enableVideoPreloadMetadata ? 'metadata' : 'none'}
		></audio>
	{:else}
		<hls-video
			use:bindHls
			src={activeSrc}
			type={isHls(activeSrc) ? 'application/vnd.apple.mpegurl' : 'video/mp4'}
			poster={preferences.showVideoThumbnail ? poster : ''}
			crossorigin={usingProxy ? 'anonymous' : undefined}
			playsinline
			muted={preferences.enableVideoMute}
			preload={preferences.enableVideoPreloadMetadata ? 'metadata' : 'none'}
		>
			{#if activeSubtitleTrack?.vttUrl}
				<track
					kind="subtitles"
					src={activeSubtitleTrack.vttUrl}
					srclang={activeSubtitleTrack.language}
					label={activeSubtitleTrack.language}
					default
				/>
			{/if}
		</hls-video>
	{/if}
{/snippet}

{#if isAudio}
	<!-- Audio: video.js audio skin (same control styling as the video player, but no
	     video frame), with a lightweight quality picker above it. dir=ltr keeps the
	     control bar stable even when the app mirrors for Farsi. -->
	<div dir="ltr" class="group relative w-full overflow-hidden rounded-md bg-black">
		<div class="flex items-center justify-between gap-3">
			{#if showQualityMenu}
				<select
					class="bg-background text-foreground rounded-lg border px-2 py-1 text-xs font-medium disabled:cursor-wait disabled:opacity-60"
					value={activeIndex}
					disabled={switching}
					onchange={(e) => switchQuality(Number(e.currentTarget.value))}
					aria-label={t('player.audioLabel')}
					aria-busy={switching}
				>
					{#each usable as q, i (i)}
						<option value={i}>{qualityLabel(q, i)}</option>
					{/each}
				</select>
			{/if}
		</div>

		{#if ready && usable.length}
			<audio-player class="block w-full" use:bindPlayerRoot>
				<audio-minimal-skin use:bindSkin>
					{@render mediaEl()}
				</audio-minimal-skin>
			</audio-player>
		{/if}

		{#if hasError || !usable.length}
			<div class="flex flex-col gap-2">
				<div class="text-warning flex items-center gap-2 text-sm">
					<TriangleAlert class="h-4 w-4 shrink-0" />
					<span>{t('player.error')}</span>
				</div>
				{#if onToggleProxy}
					<!-- Label names the route the click switches TO, so the action is
					     concrete instead of an abstract mode toggle. -->
					<Button
						variant="outline"
						size="sm"
						onclick={onToggleProxy}
						class="w-fit gap-1.5 rounded-md text-xs"
					>
						<Waypoints class="h-3 w-3" />
						{useProxy ? t('player.error.tryDirect') : t('player.error.tryViaServer')}
					</Button>
				{/if}
			</div>
		{/if}
	</div>
{:else}
	<!-- Force LTR: the video.js v10 skin doesn't lay out correctly in RTL, so the
	     player stays left-to-right even when the rest of the app mirrors for Farsi. -->
	<div
		dir="ltr"
		class="ds-player animate-in fade-in group relative aspect-video w-full overflow-hidden rounded-md bg-black duration-300"
	>
		{#if ready && usable.length}
			<video-player class="block h-full w-full" use:bindPlayerRoot>
				<video-minimal-skin use:bindSkin>
					{@render mediaEl()}

					{#if showQualityMenu}
						<!-- Slotted into the skin so it overlays correctly, even in fullscreen.
						     Light DOM, so the app's own theme tokens style it directly.
						     Visibility tracks the control bar (see bindSkin). Keyed on the
						     active group so switching format-group tabs remounts it -- which
						     closes any open menu. -->
						{#key activeGroupIndex}
							<QualityMenu
								qualities={usable}
								{activeIndex}
								{switching}
								onSwitch={switchQuality}
								{controlsVisible}
							/>
						{/key}
					{/if}
				</video-minimal-skin>
			</video-player>
		{/if}

		{#if hasError || !usable.length}
			<div
				class="absolute inset-0 z-30 flex flex-col items-center justify-center gap-3 bg-black/85 px-4 text-center"
			>
				<TriangleAlert class="text-warning h-8 w-8" />
				<p class="max-w-xs text-sm text-white/90">{t('player.error')}</p>
				{#if onToggleProxy}
					<Button
						variant="secondary"
						size="sm"
						onclick={onToggleProxy}
						class="gap-1.5 rounded-md text-xs"
					>
						<Waypoints class="h-3 w-3" />
						{useProxy ? t('player.error.tryDirect') : t('player.error.tryViaServer')}
					</Button>
				{/if}
			</div>
		{/if}
	</div>
{/if}

{#if (formatGroups.length > 1 || showFormatTabs) && !rowLayout}
	<!-- Format-kind tabs: one card, several tabs (progressive/HLS/audio-only/...)
	     -- they're all the same source, so switching tabs stays in this one
	     player instance (see switchGroup) rather than swapping components.
	     Horizontal underline strip. In row layout the PARENT card renders the tab
	     strip instead (as a column between player and details), driving switches
	     through the exposed `switchGroup` handle -- so this is suppressed there.
	     `showFormatTabs` forces the strip for a single group so local cards
	     carry the same kind badge as online tabs. -->
	<div
		class="border-border/60 mt-3 flex w-full items-stretch gap-5 border-b px-1.5 sm:px-2"
		role="tablist"
		aria-label={t('player.formatTabs')}
		aria-busy={switching}
	>
		{#each formatGroups as group, i (i)}
			<button
				type="button"
				role="tab"
				aria-selected={i === activeGroupIndex}
				disabled={switching}
				class="relative -mb-px cursor-pointer pt-1 pb-2 font-mono text-xs font-semibold tracking-wide uppercase transition-colors disabled:cursor-wait disabled:opacity-60 sm:text-sm {i ===
				activeGroupIndex
					? 'text-signal'
					: 'text-muted-foreground hover:text-foreground'}"
				onclick={() => switchGroup(i)}
			>
				{mediaKindLabel(group.type, t('player.audioLabel'), t('player.videoLabel'))}
				{#if i === activeGroupIndex}
					<span class="bg-signal absolute inset-x-0 -bottom-px h-0.5"></span>
				{/if}
			</button>
		{/each}
	</div>
{/if}

<SubtitlePanel
	bind:open={subtitlePanelOpen}
	segments={activeSubtitleTrack?.segments ?? []}
	currentTime={playerCurrentTime}
	onSeek={seekTo}
	canDownload={Boolean(activeSubtitleTrack?.srtUrl)}
	onDownload={downloadSrt}
	onGenerate={generateSubtitles}
	onCancel={cancelSubtitles}
	generating={subtitles.isRunning}
	progress={subtitles.progress}
	stepLabel={subtitles.stepLabel}
	minWords={preferences.subtitlePanelMinWords}
/>
