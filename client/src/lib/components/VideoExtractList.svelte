<script lang="ts">
	import ListVideo from '@lucide/svelte/icons/list-video';
	import { SvelteMap } from 'svelte/reactivity';
	import { toast } from 'svelte-sonner';

	import { copyUrlToClipboard } from '$lib/clipboard';
	import MediaCard from '$lib/components/MediaCard.svelte';
	import QrDialog from '$lib/components/QrDialog.svelte';
	import SourceGroupCard from '$lib/components/SourceGroupCard.svelte';
	import { allQualityLinks, buildVideosM3u, downloadTextFile, safeFilename } from '$lib/export';
	import { extraction } from '$lib/extraction.svelte';
	import { isAudioType, sourceHost } from '$lib/format';
	import { GroupRefreshTracker } from '$lib/group-refresh.svelte';
	import { i18n } from '$lib/i18n/index.svelte';
	import { appStore } from '$lib/stores/app-state.svelte';
	import type { GroupedVideo, Preferences } from '$lib/types';
	import { visibleFormatGroups } from '$lib/video-format-groups';

	const { t } = i18n;

	let { preferences }: { preferences: Preferences } = $props();

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

	// Copy/export helpers work on any set of cards — a single card ([video]) or a
	// whole source group — collecting every quality URL, honoring per-card proxy.

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
	const refreshTracker = new GroupRefreshTracker<string>();

	// Direct links (especially proxied/CDN ones) can expire; re-pull the same
	// source URL and swap in the fresh result. Removes the stale cards only
	// once the re-extraction actually succeeds, so a failed refresh doesn't
	// wipe out a still-good (if possibly stale) set of links.
	async function refreshGroup(group: SourceGroup) {
		if (!group.sourceUrl) {
			return;
		}

		await refreshTracker.run(group.key, async () => {
			const staleItems = [...group.items];
			const ok = await extraction.extractLinks(group.sourceUrl, { forceRefresh: true });

			if (ok) {
				for (const v of staleItems) {
					appStore.removeVideoExtractResultFromStore(v);
				}
			}
		});
	}

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

		for (const v of orderedResults) {
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
	<div class="mb-4">
		<!-- Screen-reader-only live region: announces the result count as it changes
		     (e.g. "5 links extracted") without moving sighted-user focus. -->
		<p class="sr-only" aria-live="polite" role="status">
			{t('extract.resultCount', { n: videoExtractResults.length })}
		</p>

		<!-- Section header -->
		<div class="mb-4 flex flex-wrap items-center justify-between gap-3">
			<h2 class="font-heading flex items-center gap-2 text-lg font-bold tracking-tight">
				<ListVideo class="text-signal h-5 w-5" />
				{t('extract.heading')}
				<span class="text-muted-foreground font-mono text-sm font-normal"
					>({videoExtractResults.length})</span
				>
			</h2>
		</div>

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
					onCopyUrl={group.sourceUrl ? () => copyUrlToClipboard(group.sourceUrl, t) : undefined}
					onExportTxt={() => exportTxtFor(group.items, sourceHost(group.sourceUrl) || 'group')}
					onExportM3u={group.items.some((v) =>
						v.formatGroups.some((g) => g.type === 'application/x-mpegURL')
					)
						? () => exportM3uFor(group.items, sourceHost(group.sourceUrl) || 'group')
						: undefined}
					showExports={preferences.showExportButtons}
					onRefresh={() => refreshGroup(group)}
					refreshing={refreshTracker.isRefreshing(group.key)}
					onRemove={() => removeGroup(group.items)}
				>
					<!-- Videos in this group -- plain content, no per-video card. A
					     hairline border-top separates the 2nd+ video from the one
					     above it; the first video needs no divider. -->
					{#each group.items as video, i (video)}
						<MediaCard
							{video}
							{preferences}
							isFirst={i === 0}
							useProxy={cardUsesProxy(video)}
							onToggleProxy={() => toggleCardProxy(video)}
							onShowQr={showQr}
							onSubtitleTrackChange={(track) => appStore.setSubtitleTrackForVideo(video, track)}
							onAudioSplitChange={(state) => appStore.setAudioSplitForVideo(video, state)}
						/>
					{/each}
				</SourceGroupCard>
			{/each}
		</div>
	</div>
{/if}

<QrDialog bind:open={qrOpen} url={qrUrl} onCopy={(url) => copyUrlToClipboard(url, t)} />
