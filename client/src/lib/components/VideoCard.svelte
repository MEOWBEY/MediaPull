<script lang="ts">
	import Captions from '@lucide/svelte/icons/captions';
	import ChevronDown from '@lucide/svelte/icons/chevron-down';
	import ChevronUp from '@lucide/svelte/icons/chevron-up';
	import Clock from '@lucide/svelte/icons/clock';
	import Copy from '@lucide/svelte/icons/copy';
	import Download from '@lucide/svelte/icons/download';
	import Loader2 from '@lucide/svelte/icons/loader-2';
	import QrCode from '@lucide/svelte/icons/qr-code';
	import Waypoints from '@lucide/svelte/icons/waypoints';
	import X from '@lucide/svelte/icons/x';
	import { toast } from 'svelte-sonner';

	import { writeClipboard } from '$lib/clipboard';
	import { Button } from '$lib/components/ui/button';
	import VideoPlayer, {
		type SubtitleState,
		type VideoPlayerHandle
	} from '$lib/components/VideoPlayer.svelte';
	import { formatBytesToMB, formatSecondsToTime } from '$lib/format';
	import { i18n } from '$lib/i18n/index.svelte';
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
	const activeGroup = $derived(
		formatGroups[activeGroupIndex] ?? formatGroups[0] ?? { type: '', qualities: [] }
	);
	const visibleQualities = $derived(activeGroup.qualities);

	// The single quality a normal user most likely wants: highest resolution
	// that still has audio. Falls back to the top of the list (which is already
	// resolution-sorted) when every quality is video-only. Powers the mobile
	// "Download" / "Copy" primary buttons so phone users don't have to expand
	// the full quality table just to grab the obvious best file.
	const bestQuality = $derived(
		visibleQualities.find((q) => !q.videoOnly) ?? visibleQualities[0]
	);

	// On mobile the full per-quality table is collapsed by default (it's the
	// densest part of the card). Desktop always shows it.
	let showAllQualities = $state(false);

	/** First existing caption track the source already provides in a usable
	 *  (WebVTT) format -- free to use, no transcription pipeline needed. */
	const existingVttTrack = $derived(video.subtitleTracks?.find((track) => track.ext === 'vtt'));

	// True as soon as the extractor's own result says a usable caption exists,
	// even before the user has clicked (which is what actually fetches/parses
	// it into `subtitleState`). Lets the CC button show its "open" state
	// immediately instead of only after the first click resolves.
	const hasCaptionSource = $derived(Boolean(subtitleState?.hasTrack) || Boolean(existingVttTrack));

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

		if (existingVttTrack) {
			// Await so the panel opens once segments are actually populated --
			// and only if the track really resolved; opening it against a
			// failed fetch would just show "no captions" under a green button.
			if (await playerHandle.useExistingTrack(existingVttTrack)) {
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
			const filename = `${video?.title}.${quality.resolution}.${quality.ext}`;

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
	<div class="overflow-hidden rounded-none sm:rounded-xl">
		<VideoPlayer
			poster={video.thumbnail}
			{formatGroups}
			{useProxy}
			{onToggleProxy}
			webpageUrl={video.webpage_url}
			duration={video.duration ?? 0}
			initialSubtitleTrack={video.subtitleTrack}
			onReady={(handle) => (playerHandle = handle)}
			onSubtitleState={(s) => (subtitleState = s)}
			onActiveGroupChange={(i) => (activeGroupIndex = i)}
			{onSubtitleTrackChange}
		/>
	</div>

	<div class="space-y-3 px-3.5 pt-3 sm:px-0">
		<!-- Title -->
		<h3
			dir="auto"
			class="line-clamp-2 font-semibold tracking-tight {preferences.enableCompact
				? 'text-sm'
				: 'text-base'}"
			title={video.title}
		>
			{video.title || t('extract.untitled')}
		</h3>

		<!-- Duration on the left, subtitle + proxy as a small
		     labeled tab-style pair on the right. -->
		<div class="flex flex-wrap items-center justify-between gap-2">
			{#if video.duration}
				<span class="hidden text-muted-foreground sm:inline-flex items-center gap-1 text-xs">
					<Clock class="h-3 w-3" />{formatSecondsToTime(video.duration)}
				</span>
			{:else}
				<span></span>
			{/if}

			<div class="bg-muted/50 ms-auto flex shrink-0 items-center gap-1 rounded-full p-0.5">
				{#if subtitleState?.isRunning}
					<!-- Progress is a status readout (spinner + stage + real percentage);
					     cancel is its own explicit button beside it, so a glance at the
					     number can't accidentally kill the job. The stage text is hidden
					     on narrow screens (the tooltip still carries it) so the pill
					     never crowds out the cancel button on mobile. -->
					<span
						class="text-muted-foreground inline-flex items-center gap-1 px-2 py-1 text-xs"
						title={subtitleState.stepLabel}
						role="status"
						aria-label={subtitleState.stepLabel}
					>
						<Loader2 class="h-3 w-3 animate-spin hidden sm:inline" />
						<span class="text-xs max-w-36 truncate inline">{subtitleState.stepLabel}</span>
						<span class="tabular-nums">{Math.round((subtitleState?.progress ?? 0) * 100)}%</span>
					</span>
					<Button
						variant="ghost"
						size="sm"
						onclick={() => playerHandle?.cancelSubtitles()}
						title={t('subtitles.cancel')}
						aria-label={t('subtitles.cancel')}
						class="hover:text-destructive gap-1 rounded-full px-1 sm:px-2 py-1 text-xs"
					>
						<X class="h-3 w-3" />
						<span class="hidden sm:inline">{t('subtitles.cancel')}</span>
					</Button>
				{:else if subtitleState?.isResolvingExisting}
					<Button variant="ghost" size="sm" disabled class="gap-1 rounded-full px-2.5 py-1 text-xs">
						<Loader2 class="h-3 w-3 animate-spin" />
						<span>{t('subtitles.open')}</span>
					</Button>
				{:else if hasCaptionSource}
					<Button
						variant="default"
						size="sm"
						onclick={subtitleAction}
						class="gap-1 rounded-full px-2.5 py-1 text-xs"
					>
						<Captions class="h-3 w-3" />
						<span>{t('subtitles.open')}</span>
					</Button>
				{:else}
					<Button
						variant="ghost"
						size="sm"
						onclick={subtitleAction}
						class="gap-1 rounded-full px-2.5 py-1 text-xs"
					>
						<Captions class="h-3 w-3" />
						<span>{t('subtitles.generate')}</span>
					</Button>
				{/if}

				<Button
					variant={useProxy ? 'default' : 'ghost'}
					size="sm"
					onclick={onToggleProxy}
					class="gap-1 rounded-full px-2.5 py-1 text-xs"
					title={t('extract.proxyMode')}
				>
					<Waypoints class="h-3 w-3" />
					<span>{t('extract.proxyMode')}</span>
				</Button>
			</div>
		</div>

		<!-- Mobile-first primary actions: the one obvious "grab the best file"
		     pair, so phone users never need to open the full quality table.
		     Hidden on sm+ where the full table is always visible. -->
		{#if bestQuality}
			<div class="flex items-center gap-2 sm:hidden">
				{#if !(activeGroup.type === 'application/x-mpegURL') || preferences.showHlsTypeDownloadButton}
					<Button
						onclick={() => downloadQuality(bestQuality)}
						class="bg-primary text-primary-foreground hover:bg-primary/90 h-11 flex-1 gap-2 rounded-full font-semibold"
					>
						<Download class="h-4 w-4" />
						<span>{t('extract.downloadBest')}</span>
						{#if bestQuality.resolution}<span class="tabular-nums opacity-80">{bestQuality.resolution}p</span>{/if}
					</Button>
				{/if}
				<Button
					variant="outline"
					onclick={() => copyToClipboard(urlForQuality(bestQuality) ?? '')}
					class="h-11 shrink-0 gap-2 rounded-full px-4"
					title={t('extract.copyBest')}
					aria-label={t('extract.copyBest')}
				>
					<Copy class="h-4 w-4" />
					<span>{t('extract.copyBest')}</span>
				</Button>
			</div>

			<!-- Toggle for the full per-quality table on mobile. -->
			<button
				type="button"
				onclick={() => (showAllQualities = !showAllQualities)}
				class="text-muted-foreground hover:text-foreground flex w-full items-center justify-center gap-1 rounded-lg py-1.5 text-xs sm:hidden"
				aria-expanded={showAllQualities}
			>
				{#if showAllQualities}
					<ChevronUp class="h-3.5 w-3.5" />
					<span>{t('extract.hideQualities')}</span>
				{:else}
					<ChevronDown class="h-3.5 w-3.5" />
					<span>{t('extract.showAllQualities', { n: visibleQualities.length })}</span>
				{/if}
			</button>
		{/if}

		<!-- Quality list -- a single bordered list with divider lines
		     between rows, instead of a stack of separately-boxed rows.
		     Reads like a compact table: badge + size on the left,
		     tight action icons on the right, row highlights on hover.
		     On mobile it's collapsed behind the toggle above; sm+ always shows it. -->
		<div
			class="border-border/50 divide-border/50 max-h-56 divide-y overflow-y-auto rounded-xl border {showAllQualities
				? ''
				: 'hidden'} sm:block"
		>
			{#each visibleQualities as quality, index (index)}
				<div
					class="bg-muted/50 hover:bg-muted flex flex-wrap items-center gap-2 px-3 py-2 transition-colors"
				>
					<div class="flex min-w-0 flex-1 items-center gap-2">
						<span
							class="bg-primary/10 text-primary min-w-11 shrink-0 rounded-md px-1.5 py-0.5 text-center text-xs font-bold"
						>
							{quality.resolution ? `${quality.resolution}p` : quality.ext.toUpperCase()}
						</span>
						<span class="text-muted-foreground shrink-0 text-xs">
							{(quality.filesize ?? 0) > 0 ? formatBytesToMB(quality.filesize ?? 0) : '—'}
						</span>
						{#if quality.videoOnly}
							<span
								class="bg-warning/15 text-warning-foreground dark:text-warning shrink-0 rounded px-1.5 py-0.5 text-[0.65rem] font-medium"
								title={t('extract.videoOnlyHint')}
							>
								{t('extract.videoOnly')}
							</span>
						{/if}
					</div>

					<div class="ms-auto flex shrink-0 items-center">
						<Button
							variant="ghost"
							size="icon"
							onclick={() => copyToClipboard(urlForQuality(quality) ?? '')}
							class="h-7 w-7 rounded-md"
							title={t('extract.copyUrl')}
							aria-label={t('extract.copyUrl')}
						>
							<Copy class="h-3.5 w-3.5" />
						</Button>
						<!-- QR is a desktop->phone handoff, so it's hidden on small screens. -->
						<Button
							variant="ghost"
							size="icon"
							onclick={() => onShowQr(urlForQuality(quality))}
							class="hidden h-7 w-7 rounded-md sm:inline-flex"
							title={t('extract.showQr')}
							aria-label={t('extract.showQr')}
						>
							<QrCode class="h-3.5 w-3.5" />
						</Button>
						{#if !(activeGroup.type === 'application/x-mpegURL') || preferences.showHlsTypeDownloadButton}
							<Button
								variant="ghost"
								size="icon"
								onclick={() => downloadQuality(quality)}
								class="h-7 w-7 rounded-md"
								title={t('extract.download')}
								aria-label={t('extract.download')}
							>
								<Download class="h-3.5 w-3.5" />
							</Button>
						{/if}
					</div>
				</div>
			{/each}
		</div>
	</div>
</div>
