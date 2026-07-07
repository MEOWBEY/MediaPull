<script lang="ts">
	import ListVideo from '@lucide/svelte/icons/list-video';
	import Search from '@lucide/svelte/icons/search';
	import { SvelteMap } from 'svelte/reactivity';
	import { toast } from 'svelte-sonner';

	import { writeClipboard } from '$lib/clipboard';
	import QrDialog from '$lib/components/QrDialog.svelte';
	import SourceGroupCard from '$lib/components/SourceGroupCard.svelte';
	import VideoCard from '$lib/components/VideoCard.svelte';
	import { allQualityLinks, buildVideosM3u, downloadTextFile, safeFilename } from '$lib/export';
	import { extraction } from '$lib/extraction.svelte';
	import { isAudioType, mediaKindLabel } from '$lib/format';
	import { i18n } from '$lib/i18n/index.svelte';
	import { appStore } from '$lib/stores/app-state.svelte';
	import type { GroupedVideo } from '$lib/types';
	import { visibleFormatGroups } from '$lib/video-format-groups';

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

	function toggleCardProxy(video: Card): void {
		proxyByCard.set(video, !cardUsesProxy(video));
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

	// Free-text filter over title, format-kind labels, and per-quality resolution/extension.
	let filterQuery = $state('');
	// Debounced so a large result set doesn't re-filter on every keystroke --
	// the input itself stays bound to the raw, undelayed value so typing never
	// feels laggy.
	let debouncedFilterQuery = $state('');

	$effect(() => {
		const value = filterQuery;
		const timer = setTimeout(() => {
			debouncedFilterQuery = value;
		}, 180);

		return () => clearTimeout(timer);
	});

	let filteredResults = $derived.by(() => {
		const q = debouncedFilterQuery.trim().toLowerCase();

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
			if (visibleFormatGroups(v, preferences).length === 0) {
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
				<SourceGroupCard
					sourceUrl={group.sourceUrl}
					itemCount={group.items.length}
					onCopyAll={() => copyLinks(group.items)}
					onExportTxt={() => exportTxtFor(group.items, sourceHost(group.sourceUrl) || 'group')}
					onExportM3u={() => exportM3uFor(group.items, sourceHost(group.sourceUrl) || 'group')}
					onRefresh={() => refreshGroup(group)}
					refreshing={refreshingGroups.get(group.key)}
					onRemove={() => removeGroup(group.items)}
				>
					<!-- Videos in this group -- plain content, no per-video card. A
					     hairline border-top separates the 2nd+ video from the one
					     above it; the first video needs no divider. -->
					{#each group.items as video, i (video)}
						<VideoCard
							{video}
							{preferences}
							isFirst={i === 0}
							useProxy={cardUsesProxy(video)}
							onToggleProxy={() => toggleCardProxy(video)}
							onShowQr={showQr}
							onSubtitleTrackChange={(track) => appStore.setSubtitleTrackForVideo(video, track)}
						/>
					{/each}
				</SourceGroupCard>
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
