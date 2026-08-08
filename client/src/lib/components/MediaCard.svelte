<script lang="ts">
	import Calendar from '@lucide/svelte/icons/calendar';
	import Clock from '@lucide/svelte/icons/clock';
	import Copy from '@lucide/svelte/icons/copy';
	import Download from '@lucide/svelte/icons/download';
	import HardDrive from '@lucide/svelte/icons/hard-drive';
	import Info from '@lucide/svelte/icons/info';
	import QrCode from '@lucide/svelte/icons/qr-code';
	import Trash2 from '@lucide/svelte/icons/trash-2';
	import { onDestroy } from 'svelte';
	import { toast } from 'svelte-sonner';

	import { splitAudioLocal, splitAudioUrl } from '$lib/api/split-audio';
	import { writeClipboard } from '$lib/clipboard';
	import AudioSplitAction from '$lib/components/AudioSplitAction.svelte';
	import SubtitleAction from '$lib/components/SubtitleAction.svelte';
	import { Button } from '$lib/components/ui/button';
	import VideoPlayer, {
		type SubtitleState,
		type VideoPlayerHandle
	} from '$lib/components/VideoPlayer.svelte';
	import { safeFilename } from '$lib/export';
	import {
		formatBytesToMB,
		formatSecondsToTime,
		formatYYYYMMDDToDate,
		isAudioType,
		mediaKindLabel
	} from '$lib/format';
	import { i18n } from '$lib/i18n/index.svelte';
	import { health } from '$lib/stores/health.svelte';
	import { localFiles, type LocalFileEntry } from '$lib/stores/local-library.svelte';
	import { ui } from '$lib/stores/ui.svelte';
	import { TranscriptionController } from '$lib/transcribe.svelte';
	import { allQualities } from '$lib/transform';
	import type { AudioSplitDone } from '$lib/stores/local-library.svelte';
	import type {
		FormatGroup,
		GroupedVideo,
		Preferences,
		SubtitleTrackResult,
		VideoFormat
	} from '$lib/types';
	import { visibleFormatGroups } from '$lib/video-format-groups';

	const { t } = i18n;

	// One card for every result: a local file (`entry`) or a URL-extracted
	// video (`video`). Local mode trims the online extras (proxy/QR/copy,
	// quality tabs, caption reuse) and adds the file's own controls (poster
	// snapshot, remove, upload-based transcription/splitting); everything else
	// — player, title, metadata, action pills, quality/download rows — is the
	// same markup, so a fix lands in one place for both.
	let {
		entry = null,
		video = null,
		preferences,
		isFirst = false,
		useProxy = true,
		onToggleProxy,
		onShowQr,
		onSubtitleTrackChange,
		onAudioSplitChange
	}: {
		/** Local mode: the open file this card renders (its blob URL powers the
		 *  player; the store owns persistence). */
		entry?: LocalFileEntry | null;
		/** URL mode: the extracted source this card renders. */
		video?: GroupedVideo | null;
		preferences: Preferences;
		isFirst?: boolean;
		useProxy?: boolean;
		onToggleProxy?: () => void;
		onShowQr?: (url: string | undefined) => void;
		onSubtitleTrackChange?: (track: SubtitleTrackResult | null) => void;
		onAudioSplitChange?: (state: AudioSplitDone | null) => void;
	} = $props();

	const isLocal = $derived(Boolean(entry));

	// ----- Player handle + subtitle state (mirrored up from VideoPlayer) ----
	let playerHandle: VideoPlayerHandle | null = null;
	let subtitleState = $state<SubtitleState | null>(null);
	let activeGroupIndex = $state(0);
	// Local files transcribe through their own controller (file upload); URL
	// videos run the player's internal resolver (see subtitleAction).
	const subtitles = new TranscriptionController();

	// ----- Format groups ----------------------------------------------------
	const localFormatGroups: FormatGroup[] = $derived.by(() => {
		if (!entry) {
			return [];
		}
		const isAudio = entry.file.type.startsWith('audio/');

		return [
			{
				type: entry.file.type || (isAudio ? 'audio/mpeg' : 'video/mp4'),
				qualities: [
					{
						proxiedVideoUrl: entry.blobUrl,
						sourceVideoUrl: entry.blobUrl,
						ext: entry.file.name.split('.').pop() ?? (isAudio ? 'mp3' : 'mp4'),
						format_id: 'local',
						protocol: 'blob',
						resolution: 0,
						tbr: 0,
						filesize: entry.file.size,
						videoOnly: false
					}
				]
			}
		];
	});

	const formatGroups = $derived(
		isLocal ? localFormatGroups : visibleFormatGroups(video!, preferences)
	);
	const isRow = $derived(preferences.layoutList === 'row');
	const activeGroup = $derived(
		formatGroups[activeGroupIndex] ?? formatGroups[0] ?? { type: '', qualities: [] }
	);
	const visibleQualities = $derived(activeGroup.qualities);

	// The kind + size a local file's row shows — no download button: the file
	// already lives on this device, so the row is info only.
	const localTitle = $derived(entry?.file.name.replace(/\.[^.]+$/, '') ?? '');
	const localExt = $derived(
		entry?.file.name.split('.').pop()?.toLowerCase() ??
			(entry?.file.type.startsWith('audio/') ? 'mp3' : 'mp4')
	);

	// ----- Local poster frame ----------------------------------------------
	// Local files have no server thumbnail, so the player would sit on a
	// black box. Snapshot one frame of the file itself (muted <video> ->
	// canvas drawImage at ~0.1s -> data URL) and hand it to the player as
	// its poster. Best-effort: a codec that can't render (audio-only, exotic
	// container) simply gets no poster.
	const POSTER_MAX_WIDTH = 640;
	let poster = $state('');
	let snapshotEl: HTMLVideoElement | null = null;

	$effect(() => {
		if (!isLocal || !preferences.showVideoThumbnail || poster || !entry) {
			return;
		}
		if (entry.file.type.startsWith('audio/')) {
			return;
		}

		const vid = document.createElement('video');

		snapshotEl = vid;
		vid.muted = true;
		vid.playsInline = true;
		vid.preload = 'metadata';
		vid.src = entry.blobUrl;

		const finish = () => {
			vid.removeEventListener('loadeddata', onLoaded);
			vid.removeEventListener('seeked', onSeeked);
			vid.removeEventListener('error', onError);
			vid.removeAttribute('src');
			if (snapshotEl === vid) {
				snapshotEl = null;
			}
		};

		const draw = () => {
			try {
				const width = vid.videoWidth;
				const height = vid.videoHeight;

				if (!width || !height) {
					return;
				}

				const scale = Math.min(1, POSTER_MAX_WIDTH / width);
				const canvas = document.createElement('canvas');

				canvas.width = Math.round(width * scale);
				canvas.height = Math.round(height * scale);
				canvas.getContext('2d')?.drawImage(vid, 0, 0, canvas.width, canvas.height);
				poster = canvas.toDataURL('image/jpeg', 0.7);
			} catch {
				// Snapshot is best-effort — a missing poster leaves the
				// player's usual black frame, which is fine.
			}
		};

		const onLoaded = () => {
			try {
				vid.currentTime = 0.1;
			} catch {
				finish();
			}
		};
		const onSeeked = () => {
			draw();
			finish();
		};
		const onError = () => finish();

		vid.addEventListener('loadeddata', onLoaded);
		vid.addEventListener('seeked', onSeeked);
		vid.addEventListener('error', onError);
	});

	onDestroy(() => {
		if (snapshotEl) {
			snapshotEl.removeAttribute('src');
			snapshotEl = null;
		}
	});

	// ----- Subtitles ---------------------------------------------------------

	// Pass a freshly generated local track back into the store (which persists
	// it); the player's SubtitleResolver will detect it via the
	// initialSubtitleTrack prop update and take over rendering.
	$effect(() => {
		if (isLocal && subtitles.track && playerHandle) {
			localFiles.setSubtitle(entry!.id, subtitles.track);
		}
	});

	async function subtitleAction(): Promise<void> {
		if (!playerHandle) {
			return;
		}

		if (subtitleState?.hasTrack) {
			playerHandle.openSubtitlePanel();

			return;
		}
		if (subtitleState?.isRunning || subtitleState?.isResolvingExisting) {
			return;
		}

		if (isLocal) {
			if (!entry) {
				return;
			}
			// Check size before uploading local media.
			if (entry.file.size > health.mediaMaxBytes) {
				const maxMb = Math.round(health.mediaMaxBytes / 1_000_000);

				toast.error(t('localFile.tooBig', { max: String(maxMb) }));

				return;
			}

			void subtitles.generate({ kind: 'file', file: entry.file });
		} else {
			// Guard: don't start transcription if the source has no audio
			// stream — saves API quota and gives immediate feedback instead
			// of a delayed server error.
			if (!hasAudioStream) {
				toast.error(t('toast.audioNoStream'));

				return;
			}

			if (existingCaptionTrack) {
				if (await playerHandle.useExistingTrack(existingCaptionTrack)) {
					playerHandle.openSubtitlePanel();
				}
			} else {
				void playerHandle.requestSubtitles();
			}
		}
	}

	/** First existing caption track the source already provides in a format the
	 *  client can parse (WebVTT or SRT) — free to use, no transcription needed
	 *  (manually-authored tracks win over auto-generated ones). */
	const existingCaptionTrack = $derived.by(() => {
		const parseable = (video?.subtitleTracks ?? []).filter(
			(track) => track.ext === 'vtt' || track.ext === 'srt'
		);

		return parseable.find((track) => !track.isAuto) ?? parseable[0];
	});

	// True as soon as the extractor's own result says a usable caption exists.
	const hasCaptionSource = $derived(
		Boolean(subtitleState?.hasTrack) ||
			(isLocal
				? subtitles.track !== null || entry?.subtitle !== null
				: Boolean(existingCaptionTrack))
	);

	// Only show the subtitle button once health has decided (no flash on
	// refresh): transcription enabled server-side, OR a track already exists
	// from the source — free to show regardless of the Groq key.
	const showSubtitles = $derived(health.loaded && (health.transcribeEnabled || hasCaptionSource));

	// The state the pill displays: local files run their own controller; URL
	// videos get it mirrored up from the player.
	const pillState = $derived({
		running: isLocal ? subtitles.isRunning : Boolean(subtitleState?.isRunning),
		resolving: isLocal ? false : Boolean(subtitleState?.isResolvingExisting),
		stepLabel: isLocal ? subtitles.stepLabel : (subtitleState?.stepLabel ?? ''),
		progress: isLocal ? subtitles.progress : (subtitleState?.progress ?? 0)
	});

	// Add the source's publish date if present (yt-dlp "YYYYMMDD").
	const publishDate = $derived(video?.upload_date ? formatYYYYMMDDToDate(video.upload_date) : '');

	// "Show video-only qualities" note: the preference (off by default) hides
	// silent adaptive streams; when it's hiding formats for THIS video, surface
	// a one-line note so users know more qualities exist behind the toggle.
	const showVideoOnlyNote = $derived(
		!isLocal &&
			allQualities(video!).length > formatGroups.reduce((n, g) => n + g.qualities.length, 0)
	);

	// Hide audio extract when every quality in every group is video-only.
	const hasAudioStream = $derived(formatGroups.some((g) => g.qualities.some((q) => !q.videoOnly)));

	// A source that already ships a standalone audio format (the M4A tab)
	// doesn't need the splitter; audio-only local files are already audio.
	const needsSplitAudio = $derived(
		isLocal ? false : hasAudioStream && !formatGroups.some((g) => isAudioType(g.type))
	);
	const isAudioOnlyLocal = $derived(isLocal && (entry?.file.type.startsWith('audio/') ?? false));
	const showSplit = $derived(
		health.loaded && health.splitAudioEnabled && (isLocal ? !isAudioOnlyLocal : needsSplitAudio)
	);

	// Local files keep the resolution-agnostic "Download" affordance only —
	// the blob belongs to this device, so copy/QR have no target audience.
	const showCopyQr = $derived(!isLocal);

	// The whole quality list (every quality's *proxied* URL) shipped to the
	// splitter so the server picks the SMALLEST sound-bearing source, the same
	// contract as transcription — see AudioSplitAction usage.
	const splitQualities = $derived(formatGroups.flatMap((g) => g.qualities));

	async function copyToClipboard(url: string) {
		if (!url) {
			toast.error(t('toast.noUrlCopy'));

			return;
		}

		if (await writeClipboard(url)) {
			toast.success(t('toast.copied'));
		} else {
			toast.error(t('toast.copyFailed'));
		}
	}

	function urlForQuality(quality: { proxiedVideoUrl?: string; sourceVideoUrl?: string }) {
		return useProxy
			? quality.proxiedVideoUrl || quality.sourceVideoUrl
			: quality.sourceVideoUrl || quality.proxiedVideoUrl;
	}

	function downloadQuality(quality: VideoFormat) {
		if (isLocal && entry) {
			const a = document.createElement('a');

			a.href = entry.blobUrl;
			a.download = `${localTitle || t('extract.untitled')}.${localExt}`;
			a.click();

			return;
		}

		try {
			const stem = safeFilename(video?.title, t('extract.untitled'));
			const qualityTag = quality.resolution ? `.${quality.resolution}p` : '';
			const filename = `${stem}${qualityTag}.${quality.ext}`;

			if (useProxy && quality.proxiedVideoUrl) {
				const base = quality.proxiedVideoUrl;
				const sep = base.includes('?') ? '&' : '?';
				const url = `${base}${sep}download=1&filename=${encodeURIComponent(filename)}`;

				// Navigate to the proxy URL — the server's Content-Disposition
				// header triggers the browser's save dialog.
				window.location.assign(url);
				toast.success(t('toast.downloadStarted', { name: filename }));
			} else {
				const url = quality.sourceVideoUrl || quality.proxiedVideoUrl || '';

				if (!url) {
					toast.error(t('toast.downloadFailed'));

					return;
				}

				window.open(url, '_blank', 'noopener');
			}
		} catch {
			toast.error(t('toast.downloadFailed'));
		}
	}

	// Added-date chip for local files (plain locale date, same as online).
	const addedAtDate = $derived(entry ? new Date(entry.addedAt).toLocaleDateString() : '');
	const showTitle = $derived(isLocal ? localTitle : video?.title || t('extract.untitled'));
	const showSrcTitle = $derived(isLocal ? entry?.file.name : video?.title);
</script>

{#if (isLocal && entry) || (!isLocal && video)}
	<div class={isFirst ? '' : 'pt-4'}>
		<!-- Local files sit directly on the page — they get their own framed
		     box. URL cards live inside the source group's box, which already
		     carries the border/background, so they stay frameless (a second
		     background behind each video reads as doubled-up chrome). -->
		<div class="rounded-lg py-3.5 {isLocal ? 'border-border/70 bg-card/60 border sm:p-4' : ''}">
			{#if isLocal}
				<!-- Local-only strip: device badge + remove. -->
				<div class="border-border/60 mb-3 flex flex-wrap items-center gap-2 border-b px-3.5 pb-2.5 sm:px-0">
					<span
						class="text-muted-foreground flex min-w-0 flex-1 items-center gap-1.5 font-mono text-xs"
					>
						<HardDrive class="h-3.5 w-3.5 shrink-0" />
						<span class="truncate">{t('localFile.onDevice')}</span>
					</span>
					<Button
						variant="ghost"
						size="icon"
						onclick={() => entry && localFiles.remove(entry.id)}
						class="text-muted-foreground hover:text-destructive h-7 w-7"
						title={t('localFile.remove')}
						aria-label={t('localFile.remove')}
					>
						<Trash2 class="h-3.5 w-3.5" />
					</Button>
				</div>
			{/if}

			<div class={isRow ? 'lg:flex lg:items-start lg:gap-3' : ''}>
				<div
					class="overflow-hidden rounded-none sm:rounded-md {isRow ? 'lg:w-full lg:max-w-xl' : ''}"
				>
					<VideoPlayer
						poster={isLocal ? poster : video?.thumbnail}
						{formatGroups}
						{useProxy}
						{onToggleProxy}
						rowLayout={isRow}
						title={showSrcTitle ?? ''}
						webpageUrl={video?.webpage_url}
						duration={video?.duration ?? 0}
						showFormatTabs={isLocal}
						initialSubtitleTrack={isLocal ? entry?.subtitle : video?.subtitleTrack}
						onReady={(handle) => (playerHandle = handle)}
						onSubtitleState={(s) => (subtitleState = s)}
						onActiveGroupChange={(i) => (activeGroupIndex = i)}
						onSubtitleTrackChange={(track) =>
							isLocal && entry
								? localFiles.setSubtitle(entry.id, track)
								: onSubtitleTrackChange?.(track)}
					/>
				</div>

				<!-- Format-kind tabs as a column BETWEEN player and details in row
				     layout (a horizontal strip below the player otherwise). Local
				     files always show their single kind tab so the card matches
				     the online look. -->
				{#if isRow && (formatGroups.length > 1 || isLocal)}
					<div
						class="border-border/60 mt-3 flex flex-row flex-wrap items-stretch gap-x-4 gap-y-1 border-b lg:mt-0 lg:w-auto lg:shrink-0 lg:flex-col lg:flex-nowrap lg:gap-1 lg:border-b-0 lg:border-s lg:pe-1"
						role="tablist"
						aria-label={t('player.formatTabs')}
					>
						{#each formatGroups as group, i (i)}
							<button
								type="button"
								role="tab"
								aria-selected={i === activeGroupIndex}
								onclick={() => playerHandle?.switchGroup(i)}
								class="px-1 relative shrink-0 cursor-pointer whitespace-nowrap font-mono text-xs font-semibold tracking-wide uppercase transition-colors sm:text-sm -mb-px pt-1 pb-2 lg:mb-0 lg:-ms-px lg:border-s-2 lg:py-1.5 lg:ps-3 lg:text-start {i ===
								activeGroupIndex
									? 'text-signal lg:border-signal'
									: 'text-muted-foreground hover:text-foreground lg:border-transparent'}"
							>
								{mediaKindLabel(group.type, t('player.audioLabel'), t('player.videoLabel'))}
								{#if i === activeGroupIndex}
									<span class="bg-signal absolute inset-x-0 -bottom-px h-0.5 lg:hidden"></span>
								{/if}
							</button>
						{/each}
					</div>
				{/if}

				<!-- Details: px keeps the title/actions off the card edge on
				     mobile (the stacked layout has no side padding otherwise);
				     desktop is flush, same as the online rows. -->
				<div class="space-y-3 px-3 pt-3 sm:px-0 {isRow ? 'lg:min-w-0 lg:flex-1 lg:pt-0' : ''}">
					<h3
						dir="auto"
						class="line-clamp-2 text-base font-semibold tracking-tight wrap-break-word"
						title={showSrcTitle}
					>
						{showTitle}
					</h3>

					<div class="flex flex-wrap items-center justify-between gap-2">
						<div class="text-muted-foreground flex min-w-0 items-center gap-3 font-mono text-xs">
							{#if !isLocal && video?.duration}
								<span class="inline-flex items-center gap-1">
									<Clock class="h-3 w-3" />{formatSecondsToTime(video.duration)}
								</span>
							{/if}
							{#if (isLocal && addedAtDate) || (!isLocal && publishDate)}
								<span
									class="inline-flex min-w-0 items-center gap-1 truncate"
									title={isLocal ? addedAtDate : publishDate}
								>
									<Calendar class="h-3 w-3 shrink-0" /><span class="truncate"
										>{isLocal ? addedAtDate : publishDate}</span
									>
								</span>
							{/if}
						</div>

						<!-- Action group: subtitles + audio split. On mobile they
						     stack full-width (subtitles on top, split below) so a
						     finished state never squeezes beside the other; from sm
						     up they sit inline at the end. -->
						<div
							class="flex w-full flex-col gap-1.5 sm:ms-auto sm:w-auto sm:flex-row sm:flex-wrap sm:items-center sm:justify-end"
						>
							{#if showSubtitles}
								<SubtitleAction
									running={pillState.running}
									resolving={pillState.resolving}
									hasTrack={hasCaptionSource}
									stepLabel={pillState.stepLabel}
									progress={pillState.progress}
									showGenerate={isLocal ? true : hasAudioStream}
									onAction={subtitleAction}
									onCancel={() => (isLocal ? subtitles.cancel() : playerHandle?.cancelSubtitles())}
								/>
							{/if}

							{#if showSplit}
								<AudioSplitAction
									run={(signal) => {
										if (isLocal) {
											if (!entry) {
												return Promise.reject(new Error('no_file'));
											}
											if (entry.file.size > health.mediaMaxBytes) {
												const maxMb = Math.round(health.mediaMaxBytes / 1_000_000);

												return Promise.reject(
													new Error(t('localFile.tooBig', { max: String(maxMb) }))
												);
											}

											return splitAudioLocal(entry.file, { signal });
										}
										if (splitQualities.length === 0) {
											return Promise.reject(new Error('no_audio_stream'));
										}

										return splitAudioUrl(splitQualities, { signal });
									}}
									filenameHint={isLocal ? localTitle : safeFilename(video?.title, 'audio')}
									persisted={isLocal ? (entry?.audioSplit ?? null) : (video?.audioSplit ?? null)}
									onDone={(state) =>
										isLocal
											? entry && localFiles.setAudioSplit(entry.id, state)
											: onAudioSplitChange?.(state)}
								/>
							{/if}
						</div>
					</div>

					{#if showVideoOnlyNote}
						<div
							class="border-border/60 bg-muted/40 text-muted-foreground flex items-start gap-2 rounded-md border px-3 py-2 text-xs"
						>
							<Info class="text-signal mt-0.5 h-3.5 w-3.5 shrink-0" />
							<p class="min-w-0 leading-relaxed">
								{t('extract.videoOnlyNote')}
								<button
									type="button"
									onclick={() => ui.openPreferences('playback')}
									class="text-signal cursor-pointer font-medium underline underline-offset-2 hover:opacity-80"
								>
									{t('extract.videoOnlyNoteAction')}
								</button>
							</p>
						</div>
					{/if}

					<!-- Quality list — a download-manager transfer log: one row per
					     format. Local files appear as a single info row (kind +
					     size) with no actions — the file already lives on this
					     device, so there's nothing to copy or re-download. -->
					<div
						class="border-border/70 divide-border/70 max-h-56 divide-y overflow-y-auto rounded-md border"
					>
						{#each visibleQualities as quality, index (index)}
							<div
								class="hover:bg-muted/60 flex flex-wrap items-center gap-2 px-3 py-2 font-mono transition-colors"
							>
								<div class="flex min-w-0 flex-1 flex-wrap items-center gap-x-2.5 gap-y-1">
									<span
										class="text-signal w-16 shrink-0 text-start text-[0.7rem] font-bold tabular-nums"
									>
										{isLocal
											? t('localFile.localTag')
											: quality.resolution
												? `${quality.resolution}p`
												: quality.ext.toUpperCase()}
									</span>
									<span class="text-muted-foreground w-16 shrink-0 text-[0.7rem] tabular-nums">
										{(quality.filesize ?? 0) > 0 ? formatBytesToMB(quality.filesize ?? 0) : '—'}
									</span>
									<span
										class="text-muted-foreground hidden w-16 shrink-0 text-[0.7rem] uppercase sm:inline"
									>
										{isLocal ? localExt : quality.resolution ? quality.ext : '—'}
									</span>
									{#if !isLocal && quality.videoOnly}
										<span
											class="bg-warning/15 text-warning-foreground dark:text-warning shrink-0 rounded-sm px-1.5 py-0.5 text-[0.65rem] font-medium"
											title={t('extract.videoOnlyHint')}
										>
											{t('extract.videoOnly')}
										</span>
									{/if}
								</div>

								{#if showCopyQr}
									<div class="ms-auto flex shrink-0 items-center gap-1">
										<Button
											variant="outline"
											size="icon"
											onclick={() => copyToClipboard(urlForQuality(quality) ?? '')}
											class="text-muted-foreground hover:text-foreground h-9 w-9 sm:h-7 sm:w-7"
											title={t('extract.copyUrl')}
											aria-label={t('extract.copyUrl')}
										>
											<Copy class="h-3.5 w-3.5" />
										</Button>
										<!-- QR is a desktop->phone handoff, hidden on small screens. -->
										<Button
											variant="outline"
											size="icon"
											onclick={() => onShowQr?.(urlForQuality(quality))}
											class="text-muted-foreground hover:text-foreground hidden h-7 w-7 sm:inline-flex"
											title={t('extract.showQr')}
											aria-label={t('extract.showQr')}
										>
											<QrCode class="h-3.5 w-3.5" />
										</Button>
										{#if !(activeGroup.type === 'application/x-mpegURL') || preferences.showHlsTypeDownloadButton}
											<Button
												size="sm"
												onclick={() => downloadQuality(quality)}
												class="ms-1 h-9 gap-1.5 px-3 sm:h-7 sm:px-2.5"
												title={t('extract.download')}
											>
												<Download class="h-3.5 w-3.5" />
												<span>{t('extract.download')}</span>
											</Button>
										{/if}
									</div>
								{/if}
							</div>
						{/each}
					</div>
				</div>
			</div>
		</div>
	</div>
{/if}
