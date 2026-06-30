<script lang="ts">
	import Check from '@lucide/svelte/icons/check';
	import SlidersHorizontal from '@lucide/svelte/icons/sliders-horizontal';
	import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
	import { onMount, tick } from 'svelte';

	import { i18n } from '$lib/i18n/index.svelte';
	import { appStore } from '$lib/stores/app-state.svelte';
	import type { VideoFormat } from '$lib/types';

	const { t } = i18n;

	let {
		poster = '',
		qualities = [],
		type = '',
		useProxy = true
	}: {
		poster?: string;
		qualities?: Partial<VideoFormat>[];
		type?: string;
		useProxy?: boolean;
	} = $props();

	// Audio-only media gets a compact native <audio> player (no video frame),
	// instead of the aspect-video skin used for visual formats.
	const isAudio = $derived(typeof type === 'string' && type.startsWith('audio/'));

	const { preferences } = appStore;

	// Both <video> and <hls-video> expose the media subset we drive (currentTime,
	// paused, play, load) but aren't the same DOM type — narrow to that.
	type MediaEl = HTMLElement &
		Pick<HTMLMediaElement, 'currentTime' | 'paused' | 'play' | 'load' | 'muted' | 'volume'>;
	type HlsEl = MediaEl & { config?: Record<string, unknown> };

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

	let videoEl: MediaEl | null = null;
	let qualityRoot: HTMLElement | null = $state(null);
	let ready = $state(false);
	let hasError = $state(false);
	let activeIndex = $state(0);
	let menuOpen = $state(false);
	// Mirrors the skin's own control-bar visibility so the quality button fades
	// in and out together with the controls.
	let controlsVisible = $state(true);

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

	function labelFor(q: Partial<VideoFormat> | undefined, i: number): string {
		if (q?.resolution) {
			return `${q.resolution}p`;
		}
		if (q?.ext) {
			return q.ext.toUpperCase();
		}

		return `Source ${i + 1}`;
	}

	const activeSrc = $derived(urlFor(usable[activeIndex]));
	// Our proxy adds `Access-Control-Allow-Origin: *`, so CORS mode is safe there.
	// Raw source URLs usually send no CORS headers — forcing crossorigin on them
	// makes the browser reject the media ("MEDIA_ELEMENT_ERROR: Format error").
	const usingProxy = $derived(activeSrc.includes('/api/proxy-video'));
	// One unified menu for every format (mp4 / mp3 / avi / hls / …): switch by
	// swapping the source URL. Shown whenever the extractor gave more than one.
	const showQualityMenu = $derived(usable.length > 1);

	async function switchQuality(index: number) {
		if (index === activeIndex || !videoEl) {
			return;
		}

		// Capture the live runtime state before the element is torn down — the fresh
		// element would otherwise reset everything to its initial attributes (so the
		// user's mute/volume/position/play state would be lost on every switch).
		const resumeTime = videoEl.currentTime;
		const wasPlaying = !videoEl.paused;
		const wasMuted = videoEl.muted;
		const prevVolume = videoEl.volume;

		activeIndex = index;
		menuOpen = false;

		// The {#key activeSrc} block tears down the old element and mounts a fresh
		// one, so wait for that to bind before driving the new element.
		await tick();
		const el = videoEl;

		if (!el) {
			return;
		}

		// Mute/volume can be applied immediately (no metadata needed), so the user's
		// sound choice survives the swap regardless of play state.
		el.muted = wasMuted;
		el.volume = prevVolume;

		// We changed `src` on the same element (no remount). A native <video> only
		// picks up a new src after an explicit load(); <hls-video> reloads itself
		// when its src attribute changes, so don't double-load it.
		if (!isHls(activeSrc)) {
			try {
				el.load();
			} catch {
				/* element may not be ready; play()/events below still recover */
			}
		}

		// Restore the playhead as soon as the new source reports its duration.
		// With preload="none" the metadata only loads once play() is called, so
		// for a paused switch this still fires on the user's next play.
		el.addEventListener(
			'loadedmetadata',
			() => {
				if (resumeTime > 0) {
					el.currentTime = resumeTime;
				}
			},
			{ once: true }
		);

		// Only force the new source to load when we were already playing — never
		// preload after a paused switch (keeps "no load before play" intact).
		if (wasPlaying) {
			void el.play().catch(() => {});
		}
	}

	// Close the quality menu when clicking anywhere outside it (the trigger itself
	// still toggles via its own onclick — it lives inside qualityRoot, so this
	// outside-handler ignores it).
	$effect(() => {
		if (!menuOpen) {
			return;
		}

		const onDocPointerDown = (event: Event) => {
			if (qualityRoot && !qualityRoot.contains(event.target as Node)) {
				menuOpen = false;
			}
		};

		document.addEventListener('pointerdown', onDocPointerDown);

		return () => document.removeEventListener('pointerdown', onDocPointerDown);
	});

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

	// hls.js reads `config` when it builds the engine, so set it before the element
	// resolves its `src`. Setting the property (not an attribute) is required.
	function bindHls(node: MediaEl) {
		(node as HlsEl).config = { ...(node as HlsEl).config, ...HLS_CONFIG };

		return bindVideo(node);
	}

	// Follow the skin's control-bar visibility. The skin is an open-shadow web
	// component that toggles `data-visible` on its `.media-controls` element; mirror
	// that onto `controlsVisible` so our slotted quality button tracks it exactly.
	function bindSkin(node: HTMLElement) {
		let observer: MutationObserver | null = null;
		let raf = 0;

		const attach = () => {
			const controls = node.shadowRoot?.querySelector('.media-controls');

			if (!controls) {
				raf = requestAnimationFrame(attach);

				return;
			}

			const sync = () => (controlsVisible = controls.hasAttribute('data-visible'));

			sync();
			observer = new MutationObserver(sync);
			observer.observe(controls, { attributes: true, attributeFilter: ['data-visible'] });
		};

		attach();

		return {
			destroy() {
				cancelAnimationFrame(raf);
				observer?.disconnect();
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
		// Audio gets the dedicated audio skin (same control styling, no video frame).
		(async () => {
			if (isAudio) {
				await import('@videojs/html/audio/minimal-skin');
			} else {
				await import('@videojs/html/video/minimal-skin');
			}
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
     its `src`; it's swapped only when the engine type changes (HLS <-> native/audio),
     driven by the {#if} below. switchQuality() reloads + restores state in place. -->
{#snippet mediaEl()}
	{#if isHls(activeSrc)}
		<hls-video
			use:bindHls
			src={activeSrc}
			poster={!isAudio && preferences.showVideoThumbnail ? poster : ''}
			crossorigin={usingProxy ? 'anonymous' : undefined}
			playsinline
			muted={preferences.enableVideoMute}
			preload={preferences.enableVideoPreloadMetadata ? 'metadata' : 'none'}
		></hls-video>
	{:else if isAudio}
		<audio
			use:bindVideo
			src={activeSrc}
			crossorigin={usingProxy ? 'anonymous' : undefined}
			muted={preferences.enableVideoMute}
			preload={preferences.enableVideoPreloadMetadata ? 'metadata' : 'none'}
		></audio>
	{:else}
		<video
			use:bindVideo
			src={activeSrc}
			poster={preferences.showVideoThumbnail ? poster : ''}
			crossorigin={usingProxy ? 'anonymous' : undefined}
			playsinline
			muted={preferences.enableVideoMute}
			preload={preferences.enableVideoPreloadMetadata ? 'metadata' : 'none'}
		></video>
	{/if}
{/snippet}

{#if isAudio}
	<!-- Audio: video.js audio skin (same control styling as the video player, but no
	     video frame), with a lightweight quality picker above it. dir=ltr keeps the
	     control bar stable even when the app mirrors for Farsi. -->
	<div dir="ltr" class="group relative w-full overflow-hidden rounded-xl bg-black">
		<div class="flex items-center justify-between gap-3">
			{#if showQualityMenu}
				<select
					class="bg-background text-foreground rounded-lg border px-2 py-1 text-xs font-medium"
					value={activeIndex}
					onchange={(e) => switchQuality(Number(e.currentTarget.value))}
					aria-label={t('player.audioLabel')}
				>
					{#each usable as q, i (i)}
						<option value={i}>{labelFor(q, i)}</option>
					{/each}
				</select>
			{/if}
		</div>

		{#if ready && usable.length}
			<audio-player class="block w-full">
				<audio-minimal-skin use:bindSkin>
					{@render mediaEl()}
				</audio-minimal-skin>
			</audio-player>
		{/if}

		{#if hasError || !usable.length}
			<div class="flex items-center gap-2 text-sm text-amber-500">
				<TriangleAlert class="h-4 w-4 shrink-0" />
				<span>{t('player.error')}</span>
			</div>
		{/if}
	</div>
{:else}
	<!-- Force LTR: the video.js v10 skin doesn't lay out correctly in RTL, so the
	     player stays left-to-right even when the rest of the app mirrors for Farsi. -->
	<div
		dir="ltr"
		class="ds-player group relative aspect-video w-full overflow-hidden rounded-xl bg-black"
	>
		{#if ready && usable.length}
			<video-player class="block h-full w-full">
				<video-minimal-skin use:bindSkin>
					{@render mediaEl()}

					{#if showQualityMenu}
						<!-- Slotted into the skin so it overlays correctly, even in fullscreen.
						     Light DOM, so the app's own theme tokens style it directly.
						     Visibility tracks the control bar (see bindSkin). -->
						<div
							bind:this={qualityRoot}
							class="ds-quality"
							data-open={menuOpen}
							data-visible={controlsVisible || menuOpen}
						>
							<button
								type="button"
								class="ds-quality__trigger"
								aria-haspopup="menu"
								aria-expanded={menuOpen}
								onclick={() => (menuOpen = !menuOpen)}
							>
								<SlidersHorizontal class="h-3.5 w-3.5" />
								<span>{labelFor(usable[activeIndex], activeIndex)}</span>
							</button>

							{#if menuOpen}
								<div class="ds-quality__menu" role="menu">
									{#each usable as q, i (i)}
										<button
											type="button"
											role="menuitemradio"
											aria-checked={i === activeIndex}
											class="ds-quality__item"
											data-active={i === activeIndex}
											onclick={() => switchQuality(i)}
										>
											<span>{labelFor(q, i)}</span>
											{#if i === activeIndex}
												<Check class="h-3.5 w-3.5" />
											{/if}
										</button>
									{/each}
								</div>
							{/if}
						</div>
					{/if}
				</video-minimal-skin>
			</video-player>
		{/if}

		{#if hasError || !usable.length}
			<div
				class="absolute inset-0 z-30 flex flex-col items-center justify-center gap-3 bg-black/85 px-4 text-center"
			>
				<TriangleAlert class="h-8 w-8 text-amber-400" />
				<p class="max-w-xs text-sm text-white/90">{t('player.error')}</p>
			</div>
		{/if}
	</div>
{/if}
