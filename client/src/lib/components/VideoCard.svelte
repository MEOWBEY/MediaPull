<script lang="ts">
	import Calendar from '@lucide/svelte/icons/calendar';
	import Captions from '@lucide/svelte/icons/captions';
	import Clock from '@lucide/svelte/icons/clock';
	import Copy from '@lucide/svelte/icons/copy';
	import Download from '@lucide/svelte/icons/download';
	import Info from '@lucide/svelte/icons/info';
	import Loader2 from '@lucide/svelte/icons/loader-2';
	import QrCode from '@lucide/svelte/icons/qr-code';
	import X from '@lucide/svelte/icons/x';
	import { toast } from 'svelte-sonner';

	import { writeClipboard } from '$lib/clipboard';
	import { Button } from '$lib/components/ui/button';
	import VideoPlayer, {
		type SubtitleState,
		type VideoPlayerHandle
	} from '$lib/components/VideoPlayer.svelte';
	import { safeFilename } from '$lib/export';
	import { formatBytesToMB, formatSecondsToTime, formatYYYYMMDDToDate, mediaKindLabel } from '$lib/format';
	import { i18n } from '$lib/i18n/index.svelte';
	import { ui } from '$lib/stores/ui.svelte';
	import { allQualities } from '$lib/transform';
	import type { GroupedVideo, Preferences, SubtitleTrackResult, VideoFormat } from '$lib/types';
	import { visibleFormatGroups } from '$lib/video-format-groups';

	const { t } = i18n;

	// One video's player + title + subtitle/proxy pill row + quality list --
	// everything specific to a single card, split out of VideoExtractList so
	// that file only owns grouping/filtering, not per-card state.
	let {
		video,
		preferences,
		useProxy,
		isFirst,
		onToggleProxy,
		onShowQr,
		onSubtitleTrackChange
	}: {
		video: GroupedVideo;
		preferences: Preferences;
		useProxy: boolean;
		isFirst: boolean;
		onToggleProxy: () => void;
		onShowQr: (url: string | undefined) => void;
		onSubtitleTrackChange: (track: SubtitleTrackResult | null) => void;
	} = $props();

	// Imperative handle from the rendered VideoPlayer (see its `onReady` prop)
	// so the subtitle pill can trigger generation/panel-open without a
	// `bind:this` ref.
	let playerHandle: VideoPlayerHandle | null = null;
	// Reactive subtitle state pushed up from VideoPlayer (see its
	// `onSubtitleState`), so the pill can show generate / spinner+% / open.
	let subtitleState = $state<SubtitleState | null>(null);
	// Active format-group tab, reported up by VideoPlayer's onActiveGroupChange.
	let activeGroupIndex = $state(0);

	const formatGroups = $derived(visibleFormatGroups(video, preferences));
	const isRow = $derived(preferences.layoutList === 'row');
	const activeGroup = $derived(
		formatGroups[activeGroupIndex] ?? formatGroups[0] ?? { type: '', qualities: [] }
	);
	const visibleQualities = $derived(activeGroup.qualities);

	/** First existing caption track the source already provides in a format the
	 *  client can parse (WebVTT or SRT -- see `parseVtt`) -- free to use, no
	 *  transcription pipeline needed. Manually-authored tracks win over
	 *  auto-generated ones. */
	const existingCaptionTrack = $derived.by(() => {
		const parseable = (video.subtitleTracks ?? []).filter(
			(track) => track.ext === 'vtt' || track.ext === 'srt'
		);

		return parseable.find((track) => !track.isAuto) ?? parseable[0];
	});

	// Source publish date (yt-dlp "YYYYMMDD"). Shown whenever present.
	const publishDate = $derived(
		video.upload_date ? formatYYYYMMDDToDate(video.upload_date) : ''
	);

	// The "Show video-only qualities" preference (off by default) hides silent
	// adaptive streams -- on some sources those are all the higher resolutions.
	// When that filter is hiding formats for THIS video (detected from the
	// format metadata, so it works for any site), surface a one-line note so
	// users know more qualities exist behind the Settings toggle.
	const showVideoOnlyNote = $derived(
		allQualities(video).length > formatGroups.reduce((n, g) => n + g.qualities.length, 0)
	);

	// True as soon as the extractor's own result says a usable caption exists,
	// even before the user has clicked (which is what actually fetches/parses
	// it into `subtitleState`). Lets the CC button show its "open" state
	// immediately instead of only after the first click resolves.
	const hasCaptionSource = $derived(Boolean(subtitleState?.hasTrack) || Boolean(existingCaptionTrack));

	// The subtitles/CC action for this card. One button covers the whole flow:
	// open the panel if a track already exists, else reuse an existing caption
	// track when the source has one, else kick off transcription. Subtitles are
	// per-video (not per-quality) -- MP4/HLS/audio are the same source, so one
	// track serves them all.
	async function subtitleAction(): Promise<void> {
		if (!playerHandle) {
			return;
		}

		if (subtitleState?.hasTrack) {
			playerHandle.openSubtitlePanel();

			return;
		}

		// Resolving an existing track can take a moment -- without this a second
		// click while it's in flight (the button looks unresponsive otherwise)
		// would open the panel early against stale state, or double up on work.
		if (subtitleState?.isRunning || subtitleState?.isResolvingExisting) {
			return;
		}

		if (existingCaptionTrack) {
			// Await so the panel opens once segments are actually populated --
			// and only if the track really resolved; opening it against a
			// failed fetch would just show "no captions" under a green button.
			if (await playerHandle.useExistingTrack(existingCaptionTrack)) {
				playerHandle.openSubtitlePanel();
			}
		} else {
			void playerHandle.requestSubtitles();
		}
	}

	function urlForQuality(quality: { proxiedVideoUrl?: string; sourceVideoUrl?: string }) {
		return useProxy
			? quality.proxiedVideoUrl || quality.sourceVideoUrl
			: quality.sourceVideoUrl || quality.proxiedVideoUrl;
	}

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

	function downloadQuality(quality: VideoFormat) {
		try {
			const stem = safeFilename(video?.title, t('extract.untitled'));
			// Formats without a numeric resolution (audio-only, unknown) skip the
			// quality tag instead of embedding a meaningless "0".
			const qualityTag = quality.resolution ? `.${quality.resolution}p` : '';
			const filename = `${stem}${qualityTag}.${quality.ext}`;

			if (useProxy && quality.proxiedVideoUrl) {
				const base = quality.proxiedVideoUrl;
				const sep = base.includes('?') ? '&' : '?';
				const url = `${base}${sep}download=1&filename=${encodeURIComponent(filename)}`;

				// Navigate to the proxy URL — the server's Content-Disposition
				// header triggers the browser's save dialog. No link.click()
				// needed (and avoided — it starts downloading before the user
				// picks a save location).

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
</script>

<div class={isFirst ? '' : 'pt-4'}>
	<!-- Row layout: player fixed on the reading-start side, details take the rest.
	     Kicks in at `lg` (roomy desktop); below that the card stacks, identical to
	     grid/mobile. `lg:flex-row` uses logical direction so RTL/Farsi mirrors it. -->
	<div class={isRow ? 'lg:flex lg:items-start lg:gap-3' : ''}>
		<div
			class="overflow-hidden rounded-none sm:rounded-md {isRow
				? 'lg:w-[28rem] lg:shrink-0 xl:w-[32rem]'
				: ''}"
		>
			<VideoPlayer
				poster={video.thumbnail}
				{formatGroups}
				{useProxy}
				{onToggleProxy}
				rowLayout={isRow}
				title={video.title}
				webpageUrl={video.webpage_url}
				duration={video.duration ?? 0}
				initialSubtitleTrack={video.subtitleTrack}
				onReady={(handle) => (playerHandle = handle)}
				onSubtitleState={(s) => (subtitleState = s)}
				onActiveGroupChange={(i) => (activeGroupIndex = i)}
				{onSubtitleTrackChange}
			/>
		</div>

		<!-- Format-kind tabs as a column BETWEEN the player and details in row
		     layout. On mobile (stacked) it's a horizontal strip below the player;
		     at lg it becomes a slim vertical rail beside the player. The player
		     itself suppresses its own tab strip in row layout (see `rowLayout`),
		     and switching is driven back through the player handle so it stays one
		     instance. Only rendered when there's more than one format to switch. -->
		{#if isRow && formatGroups.length > 1}
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
						{mediaKindLabel(group.type, t('player.audioLabel'))}
						{#if i === activeGroupIndex}
							<span class="bg-signal absolute inset-x-0 -bottom-px h-0.5 lg:hidden"></span>
						{/if}
					</button>
				{/each}
			</div>
		{/if}

		<div class="space-y-3 px-3.5 pt-3 sm:px-0 {isRow ? 'lg:min-w-0 lg:flex-1 lg:pt-0' : ''}">
		<!-- Title -->
		<!-- wrap-break-word: unbroken URL-like titles must wrap inside the clamp
		     instead of clipping mid-glyph at the card edge. -->
		<h3
			dir="auto"
			class="line-clamp-2 text-base font-semibold tracking-tight wrap-break-word"
			title={video.title}
		>
			{video.title || t('extract.untitled')}
		</h3>

		<!-- Metadata (duration + publish date) on the start side; the subtitles (CC)
		     control on the end side. Both metadata chips show on mobile too. -->
		<div class="flex flex-wrap items-center justify-between gap-2">
			<div class="text-muted-foreground flex min-w-0 items-center gap-3 font-mono text-xs">
				{#if video.duration}
					<span class="inline-flex items-center gap-1">
						<Clock class="h-3 w-3" />{formatSecondsToTime(video.duration)}
					</span>
				{/if}
				{#if publishDate}
					<span class="inline-flex min-w-0 items-center gap-1 truncate" title={publishDate}>
						<Calendar class="h-3 w-3 shrink-0" /><span class="truncate">{publishDate}</span>
					</span>
				{/if}
			</div>

			<!-- Full-width on phone widths in EVERY state: the control swaps between
			     a short "Generate" pill and a much wider progress readout (label +
			     % + cancel), and a content-sized pill would jump in size and shove
			     the row around at the moment of the click. Content-sized from sm up. -->
			<div class="flex w-full min-w-0 items-center gap-1.5 sm:ms-auto sm:w-auto sm:shrink">
				{#if subtitleState?.isRunning}
					<!-- Progress is a status readout (spinner + stage + real percentage);
					     cancel is its own explicit button beside it, so a glance at the
					     number can't accidentally kill the job. The stage text truncates
					     (the tooltip carries the full label) so it never crowds out the
					     cancel button. -->
					<div class="border-border/70 flex w-full min-w-0 items-center overflow-hidden rounded-md border sm:w-auto">
						<span
							class="text-muted-foreground inline-flex min-w-0 flex-1 items-center gap-1 px-2 py-1.5 font-mono text-xs sm:flex-none"
							title={subtitleState.stepLabel}
							role="status"
							aria-label={subtitleState.stepLabel}
						>
							<Loader2 class="h-3 w-3 shrink-0 animate-spin" />
							<span class="inline min-w-0 max-w-36 truncate text-xs">{subtitleState.stepLabel}</span>
							<span class="ms-auto tabular-nums sm:ms-0">{Math.round((subtitleState?.progress ?? 0) * 100)}%</span>
						</span>
						<button
							type="button"
							onclick={() => playerHandle?.cancelSubtitles()}
							title={t('subtitles.cancel')}
							aria-label={t('subtitles.cancel')}
							class="border-border/70 text-muted-foreground hover:bg-muted hover:text-destructive flex shrink-0 items-center gap-1 border-s px-2 py-2 font-mono text-xs transition-colors sm:py-1.5"
						>
							<X class="h-3 w-3" />
							<span class="hidden sm:inline">{t('subtitles.cancel')}</span>
						</button>
					</div>
				{:else if subtitleState?.isResolvingExisting}
					<span
						class="border-border/70 text-muted-foreground animate-in fade-in flex w-full items-center justify-center gap-1.5 rounded-md border px-2.5 py-2 font-mono text-sm sm:w-auto sm:py-1.5"
					>
						<Loader2 class="h-3.5 w-3.5 animate-spin" />
						<span class="truncate">{t('subtitles.open')}</span>
					</span>
				{:else if hasCaptionSource}
					<!-- Prominent once a caption actually exists: opening it is free. -->
					<button
						type="button"
						onclick={subtitleAction}
						title={t('subtitles.openHint')}
						class="border-signal/40 bg-signal/15 text-signal animate-in fade-in flex w-full min-w-0 items-center justify-center gap-1.5 rounded-md border px-2.5 py-2 font-mono text-sm font-semibold transition-colors hover:bg-signal/25 sm:w-auto sm:justify-start sm:py-1.5"
					>
						<Captions class="h-3.5 w-3.5 shrink-0" />
						<span class="truncate">{t('subtitles.open')}</span>
					</button>
				{:else}
					<!-- Quiet by default: "Generate" starts paid transcription, so it
					     shouldn't look like a primary tap. -->
					<button
						type="button"
						onclick={subtitleAction}
						title={t('subtitles.generateHint')}
						class="border-border/70 text-muted-foreground hover:bg-muted hover:text-foreground animate-in fade-in flex w-full min-w-0 items-center justify-center gap-1.5 rounded-md border px-2.5 py-2 font-mono text-sm transition-colors sm:w-auto sm:justify-start sm:py-1.5"
					>
						<Captions class="h-3.5 w-3.5 shrink-0" />
						<span class="truncate">{t('subtitles.generate')}</span>
					</button>
				{/if}
			</div>
		</div>

		<!-- Quality list — a download-manager transfer log: mono, tabular, one row
		     per format with a signal-accented resolution tag, size, optional
		     video-only flag, and tight action icons. Hairline dividers between
		     rows. Same layout on mobile and desktop. -->
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
		<div
			class="border-border/70 divide-border/70 max-h-56 divide-y overflow-y-auto rounded-md border"
		>
			{#each visibleQualities as quality, index (index)}
				<div
					class="hover:bg-muted/60 flex flex-wrap items-center gap-2 px-3 py-2 font-mono transition-colors"
				>
					<!-- Fixed-width label columns (resolution / size / container) so the
					     values line up vertically across rows, transfer-log style.
					     flex-wrap: every column is shrink-0, so on narrow rows the
					     "no sound" badge must wrap under the columns — without it the
					     badge overflows onto the action buttons. -->
					<div class="flex min-w-0 flex-1 flex-wrap items-center gap-x-2.5 gap-y-1">
						<span
							class="text-signal w-12 shrink-0 text-start text-[0.7rem] font-bold tabular-nums"
						>
							{quality.resolution ? `${quality.resolution}p` : quality.ext.toUpperCase()}
						</span>
						<span class="text-muted-foreground w-16 shrink-0 text-[0.7rem] tabular-nums">
							{(quality.filesize ?? 0) > 0 ? formatBytesToMB(quality.filesize ?? 0) : '—'}
						</span>
						<span class="text-muted-foreground hidden w-12 shrink-0 text-[0.7rem] uppercase sm:inline">
							{quality.ext}
						</span>
						{#if quality.videoOnly}
							<span
								class="bg-warning/15 text-warning-foreground dark:text-warning shrink-0 rounded-sm px-1.5 py-0.5 text-[0.65rem] font-medium"
								title={t('extract.videoOnlyHint')}
							>
								{t('extract.videoOnly')}
							</span>
						{/if}
					</div>

					<div class="ms-auto flex shrink-0 items-center gap-1">
						<!-- Copy + QR are secondary but need to read as buttons: hairline
						     border so they don't disappear into the panel. Taller on
						     touch widths (thumb target), compact from sm up. -->
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
						<!-- QR is a desktop->phone handoff, so it's hidden on small screens. -->
						<Button
							variant="outline"
							size="icon"
							onclick={() => onShowQr(urlForQuality(quality))}
							class="text-muted-foreground hover:text-foreground hidden h-7 w-7 sm:inline-flex"
							title={t('extract.showQr')}
							aria-label={t('extract.showQr')}
						>
							<QrCode class="h-3.5 w-3.5" />
						</Button>
						<!-- Download is the primary action — accent-filled, labeled. -->
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
				</div>
			{/each}
		</div>
	</div>
	</div>
</div>
