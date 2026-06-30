<script lang="ts">
	import Check from '@lucide/svelte/icons/check';
	import Clock from '@lucide/svelte/icons/clock';
	import Copy from '@lucide/svelte/icons/copy';
	import Download from '@lucide/svelte/icons/download';
	import FileText from '@lucide/svelte/icons/file-text';
	import Link from '@lucide/svelte/icons/link';
	import ListMusic from '@lucide/svelte/icons/list-music';
	import ListVideo from '@lucide/svelte/icons/list-video';
	import MoreVertical from '@lucide/svelte/icons/more-vertical';
	import QrCode from '@lucide/svelte/icons/qr-code';
	import Search from '@lucide/svelte/icons/search';
	import Trash2 from '@lucide/svelte/icons/trash-2';
	import Waypoints from '@lucide/svelte/icons/waypoints';
	import { SvelteMap } from 'svelte/reactivity';
	import { toast } from 'svelte-sonner';

	import { writeClipboard } from '$lib/clipboard';
	import QrDialog from '$lib/components/QrDialog.svelte';
	import { Button } from '$lib/components/ui/button';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu';
	import VideoPlayer from '$lib/components/VideoPlayer.svelte';
	import { allQualityLinks, buildVideosM3u, downloadTextFile, safeFilename } from '$lib/export';
	import { formatBytesToMB, formatSecondsToTime, formatYYYYMMDDToDate } from '$lib/format';
	import { i18n } from '$lib/i18n/index.svelte';
	import { appStore } from '$lib/stores/app-state.svelte';
	import type { GroupedVideo, VideoFormat } from '$lib/types';

	const { t } = i18n;

	let {
		isExtractBusy = false,
		preferences
	} = $props();

	let videoExtractResults = $derived(appStore.videoExtractResults);

	function isAudio(type: string) {
		return typeof type === 'string' && type.startsWith('audio/');
	}

	// Organize cards: video first, then audio. Order within each group is
	// preserved (newest-last, as stored).
	let orderedResults = $derived([
		...videoExtractResults.filter((v) => !isAudio(v.type)),
		...videoExtractResults.filter((v) => isAudio(v.type))
	]);

	type Card = GroupedVideo;

	// Per-card proxy override. Each card falls back to the global preference until
	// the user flips it for that card specifically.
	const proxyByCard = new SvelteMap<Card, boolean>();

	function cardUsesProxy(video: Card): boolean {
		return proxyByCard.get(video) ?? preferences.enableProxyForVideoExtract;
	}

	function toggleCardProxy(video: Card): void {
		proxyByCard.set(video, !cardUsesProxy(video));
	}

	// Qualities to actually show. By default we hide adaptive video-only (no-audio)
	// streams — on YouTube those are everything above 360p and play silently. Users
	// who want them (e.g. to download a high-res file and merge audio themselves)
	// can flip the "Show video-only qualities" preference on.
	function visibleQualities(video: Card) {
		if (preferences.showVideoOnlyFormats) {
			return video.qualities;
		}

		return video.qualities.filter((q) => !q.videoOnly);
	}

	function clearVideoExtractResults() {
		appStore.clearVideoExtractResultsFromStore();
		toast.info(t('toast.extractCleared'));
	}

	function removeVideoExtractResult(video: Card) {
		appStore.removeVideoExtractResultFromStore(video);
		toast.info(t('toast.itemRemoved'));
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

	// Friendly, organized labels: streaming protocols, then audio "<codec> Audio",
	// then video "<container> Video". Falls back to the raw subtype.
	const AUDIO_LABELS: Record<string, string> = {
		'audio/mpeg': 'MP3',
		'audio/aac': 'AAC',
		'audio/ogg': 'OGG',
		'audio/wav': 'WAV',
		'audio/flac': 'FLAC',
		'audio/mp4': 'M4A',
		'audio/opus': 'Opus'
	};
	const VIDEO_LABELS: Record<string, string> = {
		'video/mp4': 'MP4',
		'video/webm': 'WebM',
		'video/x-matroska': 'MKV',
		'video/quicktime': 'MOV',
		'video/x-msvideo': 'AVI'
	};

	function shortType(type: string) {
		if (type === 'application/x-mpegURL') {
			return 'HLS';
		}
		if (type === 'application/dash+xml') {
			return 'DASH';
		}
		if (AUDIO_LABELS[type]) {
			return `${AUDIO_LABELS[type]} ${t('player.audioLabel')}`;
		}
		if (VIDEO_LABELS[type]) {
			return `${VIDEO_LABELS[type]} Video`;
		}
		if (isAudio(type)) {
			return `${type.split('/')[1]?.toUpperCase()} ${t('player.audioLabel')}`;
		}

		return type.split('/')[1]?.toUpperCase() ?? type;
	}

	// Free-text filter over title, type label, and per-quality resolution/extension.
	let filterQuery = $state('');

	let filteredResults = $derived.by(() => {
		const q = filterQuery.trim().toLowerCase();

		if (!q) {
			return orderedResults;
		}

		return orderedResults.filter((v) => {
			const haystack = [
				v.title ?? '',
				v.type,
				shortType(v.type),
				v.webpage_url ?? '',
				...v.qualities.map((qq) => (qq.resolution ? `${qq.resolution}p` : '')),
				...v.qualities.map((qq) => qq.ext ?? '')
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
			if (visibleQualities(v).length === 0) {
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
	<section class="mb-10">
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
			<!-- Copy/export now live per source-group; the header just clears everything. -->
			<button
				type="button"
				onclick={clearVideoExtractResults}
				class="text-muted-foreground hover:bg-destructive/10 hover:text-destructive flex h-9 w-9 items-center justify-center rounded-full transition-colors"
				title={t('extract.clear')}
				aria-label={t('extract.clear')}
			>
				<Trash2 class="h-5 w-5" />
			</button>
		</div>

		<!-- Filter — only worth showing once there's more than one card. -->
		{#if videoExtractResults.length > 1}
			<div class="relative mb-4 max-w-sm">
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

		<!-- Source groups: everything pulled from one page sits in one panel. On
		     mobile the panel chrome (border/padding/round) is dropped so each video
		     card uses the full screen width — nested "card-in-card" padding made the
		     player needlessly small on phones. The rich panel returns at sm+. -->
		{#each groups as group (group.key)}
			<div
				class="mb-6 sm:p-4 sm:border sm:rounded-4xl sm:border-border/60 sm:bg-card/30 sm:shadow-soft"
			>
				<!-- Group header: the origin page + group-wide actions -->
				<div class="border-border/50 mb-3 flex items-center gap-2 border-b pb-2 sm:mb-4 sm:pb-3">
					<Link class="text-aurora-1 h-4 w-4 shrink-0" />
					<!-- Count + URL are one cluster so the badge always hugs the URL: in
					     front of it in LTR, behind it in RTL. `me-auto` on the cluster eats
					     the free space and pushes the menu to the far end, so the badge never
					     drifts over next to the kebab. -->
					<div class="me-auto flex min-w-0 items-center gap-2">
						{#if group.sourceUrl}
							<!-- External origin page, not in-app navigation, so resolve() doesn't apply. -->
							<!-- eslint-disable svelte/no-navigation-without-resolve -->
							<!-- No dir="ltr" here: that pinned text-start to the left in every
							     locale. Letting it inherit the page dir makes the URL align to the
							     start edge (right in RTL/Farsi); <bdi> keeps the URL itself readable
							     left-to-right regardless of surrounding direction. -->
							<a
								href={group.sourceUrl}
								target="_blank"
								rel="noreferrer noopener"
								title={group.sourceUrl}
								class="text-foreground/80 hover:text-foreground min-w-0 truncate text-start text-sm font-medium underline-offset-2 hover:underline"
							>
								<bdi>{group.sourceUrl}</bdi>
							</a>
							<!-- eslint-enable svelte/no-navigation-without-resolve -->
						{:else}
							<span class="text-muted-foreground min-w-0 truncate text-sm"
								>{t('extract.sourceUnknown')}</span
							>
						{/if}
						<span
							class="bg-muted text-muted-foreground shrink-0 rounded-full px-2 py-0.5 text-xs font-medium"
							>{group.items.length}</span
						>
					</div>
					<DropdownMenu.Root>
						<DropdownMenu.Trigger>
							{#snippet child({ props })}
								<button
									{...props}
									type="button"
									class="text-muted-foreground hover:bg-muted hover:text-foreground flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition-colors"
									title={t('extract.groupMenu')}
									aria-label={t('extract.groupMenu')}
								>
									<MoreVertical class="h-4 w-4" />
								</button>
							{/snippet}
						</DropdownMenu.Trigger>
						<DropdownMenu.Content align="end" class="min-w-48">
							<DropdownMenu.Item onclick={() => copyLinks(group.items)}>
								<Copy class="h-4 w-4" />
								{t('extract.copyAll')}
							</DropdownMenu.Item>
							<DropdownMenu.Item
								onclick={() => exportTxtFor(group.items, sourceHost(group.sourceUrl) || 'group')}
							>
								<FileText class="h-4 w-4" />
								{t('extract.exportTxt')}
							</DropdownMenu.Item>
							<DropdownMenu.Item
								onclick={() => exportM3uFor(group.items, sourceHost(group.sourceUrl) || 'group')}
							>
								<ListMusic class="h-4 w-4" />
								{t('extract.exportM3u')}
							</DropdownMenu.Item>
							<DropdownMenu.Separator />
							<DropdownMenu.Item variant="destructive" onclick={() => removeGroup(group.items)}>
								<Trash2 class="h-4 w-4" />
								{t('extract.removeGroup')}
							</DropdownMenu.Item>
						</DropdownMenu.Content>
					</DropdownMenu.Root>
				</div>

				<!-- Cards in this group -->
				<div
					class="grid gap-3 sm:gap-5 {preferences.layoutList === 'grid'
						? 'grid-cols-1 lg:grid-cols-2'
						: 'grid-cols-1'}"
				>
					{#each group.items as video, i (video)}
						<article
							class="ds-glow-ring bg-card/60 shadow-soft group relative overflow-hidden border transition-shadow duration-300 {i %
								2 ===
							0
								? 'rounded-[1.75rem]'
								: 'rounded-[2.1rem]'}"
						>
							<VideoPlayer
								poster={video.thumbnail}
								qualities={visibleQualities(video)}
								type={video.type}
								useProxy={cardUsesProxy(video)}
							/>

							<div class="space-y-3 p-3 sm:p-4">
								<!-- Title + meta -->
								<div>
									<h3
										dir="auto"
										class="mx-2 line-clamp-2 font-semibold tracking-tight {preferences.enableCompact
											? 'text-sm'
											: 'text-base'}"
										title={video.title}
									>
										{video.title || t('extract.untitled')}
									</h3>

									<!-- Meta row + card menu. The ⋮ menu lives at the end of this row
							     (not beside the title) so it never sits "behind" an RTL/LTR
							     title; the meta text wraps and the menu stays pinned to the end. -->
									<div class="mt-1.5 flex items-start justify-between gap-2">
										<div
											class="text-muted-foreground flex min-w-0 flex-1 flex-wrap items-center gap-x-3 gap-y-1 text-xs"
										>
											<span class="bg-muted rounded px-1.5 py-0.5 font-medium"
												>{shortType(video.type)}</span
											>
											{#if video.duration}
												<span class="inline-flex items-center gap-1">
													<Clock class="h-3 w-3" />{formatSecondsToTime(video.duration)}
												</span>
											{/if}
											{#if video.upload_date}
												<span>{formatYYYYMMDDToDate(video.upload_date)}</span>
											{/if}
											<span
												>{visibleQualities(video).length}
												{visibleQualities(video).length === 1
													? t('extract.qualityOne')
													: t('extract.qualityMany')}</span
											>
										</div>

										<!-- Kebab: proxy toggle + copy/export this card + remove. Two steps
								     to delete, so a stray tap can't wipe a card. -->
										<DropdownMenu.Root>
											<DropdownMenu.Trigger>
												{#snippet child({ props })}
													<button
														{...props}
														type="button"
														class="text-muted-foreground hover:bg-muted hover:text-foreground -me-1 -mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full transition-colors"
														title={t('extract.cardMenu')}
														aria-label={t('extract.cardMenu')}
													>
														<MoreVertical class="h-4 w-4" />
													</button>
												{/snippet}
											</DropdownMenu.Trigger>
											<DropdownMenu.Content align="end" class="min-w-48">
												<!-- Proxy toggle: leading icon matches the other items; the tick
										     sits at the trailing edge (right in LTR / start in RTL) so it
										     lines up cleanly instead of in a left gutter. Stays open. -->
												<DropdownMenu.Item
													closeOnSelect={false}
													onclick={() => toggleCardProxy(video)}
												>
													<Waypoints class="h-4 w-4" />
													{t('extract.proxyMode')}
													{#if cardUsesProxy(video)}
														<Check class="ms-auto h-4 w-4" />
													{/if}
												</DropdownMenu.Item>
												<DropdownMenu.Separator />
												<DropdownMenu.Item onclick={() => copyLinks([video])}>
													<Copy class="h-4 w-4" />
													{t('extract.copyAll')}
												</DropdownMenu.Item>
												<DropdownMenu.Item
													onclick={() => exportTxtFor([video], video.title ?? 'video')}
												>
													<FileText class="h-4 w-4" />
													{t('extract.exportTxt')}
												</DropdownMenu.Item>
												<DropdownMenu.Item
													onclick={() => exportM3uFor([video], video.title ?? 'video')}
												>
													<ListMusic class="h-4 w-4" />
													{t('extract.exportM3u')}
												</DropdownMenu.Item>
												<DropdownMenu.Separator />
												<DropdownMenu.Item
													variant="destructive"
													onclick={() => removeVideoExtractResult(video)}
												>
													<Trash2 class="h-4 w-4" />
													{t('extract.remove')}
												</DropdownMenu.Item>
											</DropdownMenu.Content>
										</DropdownMenu.Root>
									</div>
								</div>

								<!-- Quality rail — capped height with scroll so many qualities
						     don't make the card tall. -->
								<div class="ds-quality-rail max-h-52 space-y-1.5 overflow-y-auto pr-1">
									{#each visibleQualities(video) as quality, index (index)}
										<div
											class="bg-muted/50 hover:bg-muted flex items-center justify-between gap-2 rounded-xl px-2.5 py-1.5 transition-colors"
										>
											<div class="flex min-w-0 items-center gap-2">
												<span
													class="bg-primary text-primary-foreground rounded-lg px-2 py-0.5 text-xs font-bold"
												>
													{quality.resolution
														? `${quality.resolution}p`
														: quality.ext.toUpperCase()}
												</span>
												<span class="text-muted-foreground truncate text-xs">
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

											<div class="flex items-center gap-0.5">
												<Button
													variant="ghost"
													size="icon"
													onclick={() =>
														copyToClipboard(urlForQuality(quality, cardUsesProxy(video)) ?? '')}
													class="h-8 w-8 rounded-md"
													title={t('extract.copyUrl')}
												>
													<Copy class="h-3.5 w-3.5" />
												</Button>
												<!-- QR is a desktop->phone handoff, so it's hidden on small screens. -->
												<Button
													variant="ghost"
													size="icon"
													onclick={() => showQr(urlForQuality(quality, cardUsesProxy(video)))}
													class="hidden h-8 w-8 rounded-full sm:inline-flex"
													title={t('extract.showQr')}
												>
													<QrCode class="h-3.5 w-3.5" />
												</Button>
												{#if !(video.type === 'application/x-mpegURL') || preferences.showHlsTypeDownloadButton}
													<Button
														variant="ghost"
														size="icon"
														onclick={() => downloadQuality(video, quality)}
														class="h-8 w-8 rounded-full"
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
						</article>
					{/each}
				</div>
			</div>
		{/each}
	</section>
{/if}

<!-- Loading skeleton: shown while extracting (including across a whole batch).
     Sits below any existing results so a batch shows "more loading" beneath what
     already landed; on a first extraction it's the only thing on screen. -->
{#if isExtractBusy}
	<section class="mb-10" role="status" aria-busy="true" aria-label={t('extract.loading')}>
		<span class="sr-only">{t('extract.loading')}</span>
		<div class="mb-6 sm:p-4 sm:border sm:rounded-4xl sm:border-border/60 sm:bg-card/30 sm:shadow-soft">
			<div class="border-border/50 mb-3 flex items-center gap-2 border-b pb-2 sm:mb-4 sm:pb-3">
				<div class="bg-muted h-4 w-4 shrink-0 animate-pulse rounded"></div>
				<div class="bg-muted h-4 w-48 max-w-full animate-pulse rounded"></div>
			</div>
			<div
				class="grid gap-3 sm:gap-5 {preferences.layoutList === 'grid'
					? 'grid-cols-1 lg:grid-cols-2'
					: 'grid-cols-1'}"
			>
				{#each [0, 1] as i (i)}
					<article
						class="bg-card/60 shadow-soft overflow-hidden border {i % 2 === 0
							? 'rounded-[1.75rem]'
							: 'rounded-[2.1rem]'}"
					>
						<div class="bg-muted aspect-video w-full animate-pulse"></div>
						<div class="space-y-3 p-4">
							<div class="bg-muted h-4 w-3/4 animate-pulse rounded"></div>
							<div class="bg-muted/70 h-3 w-1/2 animate-pulse rounded"></div>
							<div class="space-y-1.5 pt-1">
								<div class="bg-muted/50 h-9 animate-pulse rounded-xl"></div>
								<div class="bg-muted/50 h-9 animate-pulse rounded-xl"></div>
							</div>
						</div>
					</article>
				{/each}
			</div>
		</div>
	</section>
{/if}

<QrDialog bind:open={qrOpen} url={qrUrl} onCopy={copyToClipboard} />
