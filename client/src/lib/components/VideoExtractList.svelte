<script lang="ts">
	import Captions from '@lucide/svelte/icons/captions';
	import Clock from '@lucide/svelte/icons/clock';
	import Copy from '@lucide/svelte/icons/copy';
	import Download from '@lucide/svelte/icons/download';
	import FileText from '@lucide/svelte/icons/file-text';
	import Link from '@lucide/svelte/icons/link';
	import ListMusic from '@lucide/svelte/icons/list-music';
	import ListVideo from '@lucide/svelte/icons/list-video';
	import Loader2 from '@lucide/svelte/icons/loader-2';
	import QrCode from '@lucide/svelte/icons/qr-code';
	import RefreshCw from '@lucide/svelte/icons/refresh-cw';
	import Search from '@lucide/svelte/icons/search';
	import Trash2 from '@lucide/svelte/icons/trash-2';
	import Waypoints from '@lucide/svelte/icons/waypoints';
	import { SvelteMap } from 'svelte/reactivity';
	import { toast } from 'svelte-sonner';

	import { writeClipboard } from '$lib/clipboard';
	import QrDialog from '$lib/components/QrDialog.svelte';
	import { Button } from '$lib/components/ui/button';
	import VideoPlayer, {
		type SubtitleState,
		type VideoPlayerHandle
	} from '$lib/components/VideoPlayer.svelte';
	import { allQualityLinks, buildVideosM3u, downloadTextFile, safeFilename } from '$lib/export';
	import { extraction } from '$lib/extraction.svelte';
	import {
		formatBytesToMB,
		formatSecondsToTime,
		isAudioType,
		mediaKindLabel
	} from '$lib/format';
	import { i18n } from '$lib/i18n/index.svelte';
	import { appStore } from '$lib/stores/app-state.svelte';
	import type { FormatGroup, GroupedVideo, SubtitleTrack, VideoFormat } from '$lib/types';

	const { t } = i18n;

	let { isExtractBusy = false, preferences } = $props();

	let videoExtractResults = $derived(appStore.videoExtractResults);

	function isAudioOnlyCard(video: GroupedVideo): boolean {
		return video.formatGroups.every((g) => isAudioType(g.type));
	}

	// Organize cards: video first, then audio. Order within each group is
	// preserved (newest-last, as stored).
	let orderedResults = $derived([
		...videoExtractResults.filter((v) => !isAudioOnlyCard(v)),
		...videoExtractResults.filter((v) => isAudioOnlyCard(v))
	]);

	type Card = GroupedVideo;

	// Per-card proxy override. Each card falls back to the global preference until
	// the user flips it for that card specifically.
	const proxyByCard = new SvelteMap<Card, boolean>();

	function cardUsesProxy(video: Card): boolean {
		return proxyByCard.get(video) ?? preferences.enableProxyForVideoExtract;
	}

	// Imperative handles from each rendered VideoPlayer (see its `onReady`
	// prop) -- not reactive state, just a registry so the toolbar's Subtitles
	// button can trigger generation without a bind:this ref, which doesn't fit
	// cleanly inside this keyed {#each}.
	const playerHandles = new SvelteMap<Card, VideoPlayerHandle>();
	// Reactive per-card subtitle state pushed up from each VideoPlayer (see its
	// `onSubtitleState`), so the card's CC button can show generate / spinner+% /
	// open+download without reaching into the child.
	const subtitleState = new SvelteMap<Card, SubtitleState>();

	function registerPlayer(video: Card, handle: VideoPlayerHandle): void {
		playerHandles.set(video, handle);
	}

	/** First existing caption track the source already provides in a usable
	 *  (WebVTT) format -- free to use, no transcription pipeline needed. */
	function existingVttTrack(video: Card): SubtitleTrack | undefined {
		return (video.subtitleTracks ?? []).find((track) => track.ext === 'vtt');
	}

	// True as soon as the extractor's own result says a usable caption exists,
	// even before the user has clicked (which is what actually fetches/parses
	// it into `subtitleState`). Lets the CC button show its "open" state
	// immediately instead of only after the first click resolves.
	function hasCaptionSource(video: Card): boolean {
		return Boolean(subtitleState.get(video)?.hasTrack) || Boolean(existingVttTrack(video));
	}

	// The subtitles/CC action for a card. One button covers the whole flow:
	// open the panel if a track already exists, else reuse an existing caption
	// track when the source has one, else kick off transcription. Subtitles are
	// per-video (not per-quality) -- MP4/HLS/audio are the same source, so one
	// track serves them all.
	async function subtitleAction(video: Card): Promise<void> {
		const handle = playerHandles.get(video);

		if (!handle) {
			return;
		}

		if (subtitleState.get(video)?.hasTrack) {
			handle.openSubtitlePanel();

			return;
		}

		// Resolving an existing track can take a moment -- without this a second
		// click while it's in flight (the button looks unresponsive otherwise)
		// would open the panel early against stale state, or double up on work.
		const state = subtitleState.get(video);

		if (state?.isRunning || state?.isResolvingExisting) {
			return;
		}

		const existing = existingVttTrack(video);

		if (existing) {
			// Await so the panel opens once segments are actually populated,
			// instead of opening immediately and briefly showing "no captions".
			await handle.useExistingTrack(existing);
			handle.openSubtitlePanel();
		} else {
			void handle.requestSubtitles();
		}
	}

	function toggleCardProxy(video: Card): void {
		proxyByCard.set(video, !cardUsesProxy(video));
	}

	// Tab/list order: easiest-to-play first (progressive MP4 -- universal
	// browser support, no special handling), then everything else that still
	// needs some extra work to play (WebM/MKV/HLS/...), audio-only last.
	function groupRank(type: string): number {
		if (isAudioType(type)) {
			return 2;
		}

		return type === 'video/mp4' ? 0 : 1;
	}

	// Qualities to actually show. By default we hide adaptive video-only (no-audio)
	// streams — on YouTube those are everything above 360p and play silently. Users
	// who want them (e.g. to download a high-res file and merge audio themselves)
	// can flip the "Show video-only qualities" preference on. Also drops any
	// format-group tab left with nothing to show once that filter applies.
	function visibleFormatGroups(video: Card): FormatGroup[] {
		return video.formatGroups
			.map((g) => ({
				type: g.type,
				qualities: preferences.showVideoOnlyFormats
					? g.qualities
					: g.qualities.filter((q) => !q.videoOnly)
			}))
			.filter((g) => g.qualities.length > 0)
			.sort((a, b) => groupRank(a.type) - groupRank(b.type));
	}

	// Per-card active tab (format-group), reported up by VideoPlayer's
	// onActiveGroupChange. Indexes into `visibleFormatGroups(video)`, the same
	// (filtered) array passed to VideoPlayer as its `formatGroups` prop.
	const activeGroupByCard = new SvelteMap<Card, number>();

	function activeGroup(video: Card): FormatGroup {
		const groups = visibleFormatGroups(video);

		return groups[activeGroupByCard.get(video) ?? 0] ?? groups[0] ?? { type: '', qualities: [] };
	}

	function visibleQualities(video: Card): VideoFormat[] {
		return activeGroup(video).qualities;
	}

	let qrUrl = $state('');
	let qrOpen = $state(false);

	function showQr(url: string | undefined) {
		if (!url) {
			toast.error(t('toast.noUrlCopy'));

			return;
		}

		qrUrl = url;
		qrOpen = true;
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

	// Copy/export helpers work on any set of cards — a single card ([video]) or a
	// whole source group — collecting every quality URL, honoring per-card proxy.
	async function copyLinks(videos: Card[]) {
		const links = allQualityLinks(videos, cardUsesProxy);

		if (!links.length) {
			toast.error(t('toast.noUrlCopy'));

			return;
		}

		if (await writeClipboard(links.join('\n'))) {
			toast.success(t('toast.copiedAll', { count: links.length }));
		} else {
			toast.error(t('toast.copyFailed'));
		}
	}

	function exportTxtFor(videos: Card[], name: string) {
		const txt = allQualityLinks(videos, cardUsesProxy).join('\n');

		if (!txt) {
			toast.error(t('toast.nothingToExport'));

			return;
		}

		downloadTextFile(`${safeFilename(name)}.txt`, txt);
		toast.success(t('toast.exported'));
	}

	function exportM3uFor(videos: Card[], name: string) {
		const m3u = buildVideosM3u(videos, cardUsesProxy);

		if (m3u.trim() === '#EXTM3U') {
			toast.error(t('toast.nothingToExport'));

			return;
		}

		downloadTextFile(`${safeFilename(name)}.m3u`, m3u, 'audio/x-mpegurl');
		toast.success(t('toast.exported'));
	}

	function removeGroup(items: Card[]) {
		for (const v of [...items]) {
			appStore.removeVideoExtractResultFromStore(v);
		}
		toast.info(t('toast.itemRemoved'));
	}

	// Per-group refresh spinner -- keyed by group.key, not the items themselves
	// (those get replaced by the refresh).
	const refreshingGroups = new SvelteMap<string, boolean>();

	// Direct links (especially proxied/CDN ones) can expire; re-pull the same
	// source URL and swap in the fresh result. Removes the stale cards only
	// once the re-extraction actually succeeds, so a failed refresh doesn't
	// wipe out a still-good (if possibly stale) set of links.
	async function refreshGroup(group: SourceGroup) {
		if (!group.sourceUrl || refreshingGroups.get(group.key)) {
			return;
		}

		refreshingGroups.set(group.key, true);

		try {
			const staleItems = [...group.items];
			const ok = await extraction.extractLinks(group.sourceUrl, { forceRefresh: true });

			if (ok) {
				for (const v of staleItems) {
					appStore.removeVideoExtractResultFromStore(v);
				}
			}
		} finally {
			refreshingGroups.set(group.key, false);
		}
	}

	function sourceHost(url: string): string {
		try {
			return new URL(url).hostname.replace(/^www\./, '');
		} catch {
			return '';
		}
	}

	function urlForQuality(
		quality: { proxiedVideoUrl?: string; sourceVideoUrl?: string },
		useProxy: boolean
	) {
		return useProxy ? quality.proxiedVideoUrl : quality.sourceVideoUrl;
	}

	function downloadQuality(video: Card, quality: VideoFormat) {
		try {
			const filename = `${video?.title}.${quality.resolution}.${quality.ext}`;
			const link = document.createElement('a');

			link.href = urlForQuality(quality, cardUsesProxy(video)) ?? '';
			link.download = filename;
			link.click();
			toast.success(t('toast.downloadStarted', { name: filename }));
		} catch {
			toast.error(t('toast.downloadFailed'));
		}
	}

	// Free-text filter over title, format-kind labels, and per-quality resolution/extension.
	let filterQuery = $state('');

	let filteredResults = $derived.by(() => {
		const q = filterQuery.trim().toLowerCase();

		if (!q) {
			return orderedResults;
		}

		return orderedResults.filter((v) => {
			const allQ = v.formatGroups.flatMap((g) => g.qualities);
			const haystack = [
				v.title ?? '',
				...v.formatGroups.map((g) => g.type),
				...v.formatGroups.map((g) => mediaKindLabel(g.type, t('player.audioLabel'))),
				v.webpage_url ?? '',
				...allQ.map((qq) => (qq.resolution ? `${qq.resolution}p` : '')),
				...allQ.map((qq) => qq.ext ?? '')
			]
				.join(' ')
				.toLowerCase();

			return haystack.includes(q);
		});
	});

	interface SourceGroup {
		key: string;
		sourceUrl: string;
		items: Card[];
	}

	// Group cards by their origin page (webpage_url) so everything pulled from one
	// source sits together. Cards arrive video-first (see orderedResults), so each
	// group keeps that order. Group order follows first appearance.
	let groups = $derived.by<SourceGroup[]>(() => {
		// Transient grouping map rebuilt each derivation — not reactive state, so a
		// plain Map is correct here (a SvelteMap mutated inside $derived is unsafe).
		// eslint-disable-next-line svelte/prefer-svelte-reactivity
		const map = new Map<string, Card[]>();

		for (const v of filteredResults) {
			// Skip cards left with nothing to show once video-only is hidden.
			if (visibleFormatGroups(v).length === 0) {
				continue;
			}

			const key = v.webpage_url || v.id || 'ungrouped';
			const list = map.get(key);

			if (list) {
				list.push(v);
			} else {
				map.set(key, [v]);
			}
		}

		return [...map.entries()].map(([key, items]) => ({
			key,
			sourceUrl: items[0]?.webpage_url ?? '',
			items
		}));
	});
</script>

{#if videoExtractResults.length > 0}
	<div class="mb-10">
		<!-- Screen-reader-only live region: announces the result count as it changes
		     (e.g. "5 links extracted") without moving sighted-user focus. -->
		<p class="sr-only" aria-live="polite" role="status">
			{t('extract.resultCount', { n: videoExtractResults.length })}
		</p>

		<!-- Section header -->
		<div class="mb-4 flex flex-wrap items-center justify-between gap-3">
			<h2 class="flex items-center gap-2 text-lg font-bold tracking-tight">
				<ListVideo class="text-aurora-1 h-5 w-5" />
				{t('extract.heading')}
				<span class="text-muted-foreground font-normal">({videoExtractResults.length})</span>
			</h2>
		</div>

		<!-- Filter — only worth showing once there's more than one card. -->
		{#if videoExtractResults.length > 1}
			<div class="relative mb-5 w-full">
				<Search
					class="text-muted-foreground pointer-events-none absolute top-1/2 inset-s-3 h-4 w-4 -translate-y-1/2"
				/>
				<input
					bind:value={filterQuery}
					type="search"
					placeholder={t('extract.searchPlaceholder')}
					aria-label={t('extract.searchPlaceholder')}
					class="bg-card/60 border-border/60 focus:ring-primary/40 h-10 w-full rounded-full border ps-9 pe-3 text-sm outline-none focus:ring-2"
				/>
			</div>
		{/if}

		{#if filteredResults.length === 0}
			<p class="text-muted-foreground py-8 text-center text-sm">{t('extract.noMatches')}</p>
		{/if}

		<!-- The group is the card -- the one bordered, backed container in the
		     whole hierarchy. Groups sit in the same responsive grid so they line
		     up together; a group with several videos just stacks them inside,
		     separated by a hairline instead of each getting its own box. -->
		<div
			class="grid gap-4 sm:gap-5 {preferences.layoutList === 'grid'
				? 'grid-cols-1 lg:grid-cols-2'
				: 'grid-cols-1'}"
		>
			{#each groups as group (group.key)}
				<div
					class="border-border/60 bg-card/60 shadow-soft overflow-hidden rounded-2xl border py-3.5 sm:p-4"
				>
					<!-- Group label: origin link + group-wide actions. -->
					<div
						class="border-border/40 mb-3 flex flex-wrap items-center gap-2 border-b px-3.5 pb-2.5 sm:px-0"
					>
						<Link class="text-muted-foreground h-3.5 w-3.5 shrink-0" />
						<div class="flex min-w-0 flex-1 items-center gap-2">
							{#if group.sourceUrl}
								<!-- External origin page, not in-app navigation, so resolve() doesn't apply. -->
								<!-- eslint-disable svelte/no-navigation-without-resolve -->
								<a
									href={group.sourceUrl}
									target="_blank"
									rel="noreferrer noopener"
									title={group.sourceUrl}
									class="text-muted-foreground hover:text-foreground min-w-0 truncate text-start text-xs font-medium underline-offset-2 hover:underline"
								>
									<bdi>{group.sourceUrl}</bdi>
								</a>
								<!-- eslint-enable svelte/no-navigation-without-resolve -->
							{:else}
								<span class="text-muted-foreground min-w-0 truncate text-xs"
									>{t('extract.sourceUnknown')}</span
								>
							{/if}
							{#if group.items.length > 1}
								<span
									class="bg-muted text-muted-foreground shrink-0 rounded-full px-1.5 py-0.5 text-[0.65rem] font-semibold"
								>
									{group.items.length}
								</span>
							{/if}
						</div>
						<div class="ms-auto flex shrink-0 items-center gap-0.5">
							<Button
								variant="ghost"
								size="icon"
								onclick={() => copyLinks(group.items)}
								class="text-muted-foreground hover:text-foreground h-7 w-7 rounded-full"
								title={t('extract.copyAll')}
							>
								<Copy class="h-3.5 w-3.5" />
							</Button>
							<Button
								variant="ghost"
								size="icon"
								onclick={() => exportTxtFor(group.items, sourceHost(group.sourceUrl) || 'group')}
								class="text-muted-foreground hover:text-foreground h-7 w-7 rounded-full"
								title={t('extract.exportTxt')}
							>
								<FileText class="h-3.5 w-3.5" />
							</Button>
							<Button
								variant="ghost"
								size="icon"
								onclick={() => exportM3uFor(group.items, sourceHost(group.sourceUrl) || 'group')}
								class="text-muted-foreground hover:text-foreground h-7 w-7 rounded-full"
								title={t('extract.exportM3u')}
							>
								<ListMusic class="h-3.5 w-3.5" />
							</Button>
							<Button
								variant="ghost"
								size="icon"
								onclick={() => refreshGroup(group)}
								disabled={refreshingGroups.get(group.key)}
								class="text-muted-foreground hover:text-foreground h-7 w-7 rounded-full"
								title={t('extract.refreshGroup')}
							>
								<RefreshCw
									class="h-3.5 w-3.5 {refreshingGroups.get(group.key) ? 'animate-spin' : ''}"
								/>
							</Button>
							<Button
								variant="ghost"
								size="icon"
								onclick={() => removeGroup(group.items)}
								class="text-muted-foreground hover:text-destructive h-7 w-7 rounded-full"
								title={t('extract.removeGroup')}
							>
								<Trash2 class="h-3.5 w-3.5" />
							</Button>
						</div>
					</div>

					<!-- Videos in this group -- plain content, no per-video card. A
					     hairline border-top separates the 2nd+ video from the one
					     above it; the first video needs no divider. -->
					<div class="divide-border/50 divide-y">
						{#each group.items as video, i (video)}
							<div class={i === 0 ? '' : 'pt-4'}>
								<div class="overflow-hidden rounded-none sm:rounded-xl">
									<VideoPlayer
										poster={video.thumbnail}
										formatGroups={visibleFormatGroups(video)}
										useProxy={cardUsesProxy(video)}
										webpageUrl={video.webpage_url}
										initialSubtitleTrack={video.subtitleTrack}
										onReady={(handle) => registerPlayer(video, handle)}
										onSubtitleState={(s) => subtitleState.set(video, s)}
										onActiveGroupChange={(i) => activeGroupByCard.set(video, i)}
										onSubtitleTrackChange={(track) =>
											appStore.setSubtitleTrackForVideo(video, track)}
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
									<div class="flex items-center justify-between gap-2">
										{#if video.duration}
											<span class="text-muted-foreground inline-flex items-center gap-1 text-xs">
												<Clock class="h-3 w-3" />{formatSecondsToTime(video.duration)}
											</span>
										{:else}
											<span></span>
										{/if}

										<div class="bg-muted/50 flex shrink-0 items-center gap-0.5 rounded-full p-0.5">
											{#if subtitleState.get(video)?.isRunning}
												<Button
													variant="ghost"
													size="sm"
													disabled
													class="gap-1 rounded-full px-2.5 py-1 text-xs"
												>
													<Loader2 class="h-3 w-3 animate-spin" />
													<span>{Math.round((subtitleState.get(video)?.progress ?? 0) * 100)}%</span
													>
												</Button>
											{:else if subtitleState.get(video)?.isResolvingExisting}
												<Button
													variant="ghost"
													size="sm"
													disabled
													class="gap-1 rounded-full px-2.5 py-1 text-xs"
												>
													<Loader2 class="h-3 w-3 animate-spin" />
													<span>{t('subtitles.open')}</span>
												</Button>
											{:else if hasCaptionSource(video)}
												<Button
													variant="default"
													size="sm"
													onclick={() => subtitleAction(video)}
													class="gap-1 rounded-full px-2.5 py-1 text-xs"
												>
													<Captions class="h-3 w-3" />
													<span>{t('subtitles.open')}</span>
												</Button>
											{:else}
												<Button
													variant="ghost"
													size="sm"
													onclick={() => subtitleAction(video)}
													class="gap-1 rounded-full px-2.5 py-1 text-xs"
												>
													<Captions class="h-3 w-3" />
													<span>{t('subtitles.generate')}</span>
												</Button>
											{/if}

											<Button
												variant={cardUsesProxy(video) ? 'default' : 'ghost'}
												size="sm"
												onclick={() => toggleCardProxy(video)}
												class="gap-1 rounded-full px-2.5 py-1 text-xs"
												title={t('extract.proxyMode')}
											>
												<Waypoints class="h-3 w-3" />
												<span>{t('extract.proxyMode')}</span>
											</Button>
										</div>
									</div>

									<!-- Quality list -- a single bordered list with divider lines
									     between rows, instead of a stack of separately-boxed rows.
									     Reads like a compact table: badge + size on the left,
									     tight action icons on the right, row highlights on hover. -->
									<div
										class="border-border/50 divide-border/50 max-h-56 divide-y overflow-y-auto rounded-xl border"
									>
										{#each visibleQualities(video) as quality, index (index)}
											<div
												class="bg-muted/50 hover:bg-muted flex flex-wrap items-center gap-2 px-3 py-2 transition-colors"
											>
												<div class="flex min-w-0 flex-1 items-center gap-2">
													<span
														class="bg-primary/10 text-primary min-w-11 shrink-0 rounded-md px-1.5 py-0.5 text-center text-xs font-bold"
													>
														{quality.resolution
															? `${quality.resolution}p`
															: quality.ext.toUpperCase()}
													</span>
													<span class="text-muted-foreground shrink-0 text-xs">
														{(quality.filesize ?? 0) > 0
															? formatBytesToMB(quality.filesize ?? 0)
															: '—'}
													</span>
													{#if quality.videoOnly}
														<span
															class="bg-amber-500/15 text-amber-600 dark:text-amber-400 shrink-0 rounded px-1.5 py-0.5 text-[0.65rem] font-medium"
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
														onclick={() =>
															copyToClipboard(urlForQuality(quality, cardUsesProxy(video)) ?? '')}
														class="h-7 w-7 rounded-md"
														title={t('extract.copyUrl')}
													>
														<Copy class="h-3.5 w-3.5" />
													</Button>
													<!-- QR is a desktop->phone handoff, so it's hidden on small screens. -->
													<Button
														variant="ghost"
														size="icon"
														onclick={() => showQr(urlForQuality(quality, cardUsesProxy(video)))}
														class="hidden h-7 w-7 rounded-md sm:inline-flex"
														title={t('extract.showQr')}
													>
														<QrCode class="h-3.5 w-3.5" />
													</Button>
													{#if !(activeGroup(video).type === 'application/x-mpegURL') || preferences.showHlsTypeDownloadButton}
														<Button
															variant="ghost"
															size="icon"
															onclick={() => downloadQuality(video, quality)}
															class="h-7 w-7 rounded-md"
															title={t('extract.download')}
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
						{/each}
					</div>
				</div>
			{/each}
		</div>
	</div>
{/if}

<!-- Loading skeleton: shown while extracting (including across a whole batch).
     Sits below any existing results so a batch shows "more loading" beneath what
     already landed; on a first extraction it's the only thing on screen. Mirrors
     the single-card shell used above (no outer boxed panel). -->
{#if isExtractBusy}
	<section class="mb-10" role="status" aria-busy="true" aria-label={t('extract.loading')}>
		<span class="sr-only">{t('extract.loading')}</span>

		<div
			class="grid gap-4 sm:gap-5 {preferences.layoutList === 'grid'
				? 'grid-cols-1 lg:grid-cols-2'
				: 'grid-cols-1'}"
		>
			{#each [0, 1] as i (i)}
				<div
					class="border-border/60 bg-card/60 shadow-soft overflow-hidden rounded-2xl border py-3.5 sm:p-4"
				>
					<!-- Group label skeleton: icon + source url + action-icon cluster -->
					<div
						class="border-border/40 mb-3 flex flex-wrap items-center gap-2 border-b px-3.5 pb-2.5 sm:px-0"
					>
						<div class="bg-muted h-3.5 w-3.5 shrink-0 animate-pulse rounded-full"></div>
						<div class="bg-muted h-3.5 w-40 max-w-full animate-pulse rounded"></div>
						<div class="ms-auto flex shrink-0 items-center gap-1.5">
							{#each [0, 1, 2, 3, 4] as j (j)}
								<div class="bg-muted h-7 w-7 animate-pulse rounded-full"></div>
							{/each}
						</div>
					</div>

					<!-- Single video-item skeleton -->
					<div class="overflow-hidden rounded-none sm:rounded-xl">
						<div class="bg-muted aspect-video w-full animate-pulse"></div>
					</div>

					<div class="space-y-3 px-3.5 pt-3 sm:px-0">
						<!-- Title -->
						<div class="bg-muted h-4 w-3/4 animate-pulse rounded"></div>

						<!-- Duration + subtitle/proxy pill row -->
						<div class="flex items-center justify-between gap-2">
							<div class="bg-muted/70 h-3 w-16 animate-pulse rounded"></div>
							<div class="bg-muted/70 h-6 w-28 animate-pulse rounded-full"></div>
						</div>

						<!-- Quality list rows -->
						<div
							class="border-border/50 divide-border/50 divide-y overflow-hidden rounded-xl border"
						>
							{#each [0, 1, 2] as k (k)}
								<div class="bg-muted/50 flex items-center gap-2 px-3 py-2">
									<div class="bg-muted h-5 w-11 animate-pulse rounded-md"></div>
									<div class="bg-muted/70 h-3 w-10 animate-pulse rounded"></div>
									<div class="ms-auto flex gap-1">
										<div class="bg-muted h-7 w-7 animate-pulse rounded-md"></div>
										<div class="bg-muted h-7 w-7 animate-pulse rounded-md"></div>
									</div>
								</div>
							{/each}
						</div>
					</div>
				</div>
			{/each}
		</div>
	</section>
{/if}

<QrDialog bind:open={qrOpen} url={qrUrl} onCopy={copyToClipboard} />
