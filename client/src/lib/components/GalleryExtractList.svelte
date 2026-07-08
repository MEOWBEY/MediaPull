<script lang="ts">
	import ChevronLeft from '@lucide/svelte/icons/chevron-left';
	import ChevronRight from '@lucide/svelte/icons/chevron-right';
	import Copy from '@lucide/svelte/icons/copy';
	import Download from '@lucide/svelte/icons/download';
	import ExternalLink from '@lucide/svelte/icons/external-link';
	import ImagesIcon from '@lucide/svelte/icons/images';
	import Search from '@lucide/svelte/icons/search';
	import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
	import { SvelteMap } from 'svelte/reactivity';
	import { toast } from 'svelte-sonner';

	import { copyUrlToClipboard, writeClipboard } from '$lib/clipboard';
	import SourceGroupCard from '$lib/components/SourceGroupCard.svelte';
	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';
	import { downloadTextFile, safeFilename } from '$lib/export';
	import { extraction } from '$lib/extraction.svelte';
	import { sourceHost } from '$lib/format';
	import { GroupRefreshTracker } from '$lib/group-refresh.svelte';
	import { i18n } from '$lib/i18n/index.svelte';
	import { appStore } from '$lib/stores/app-state.svelte';
	import type { GroupedGallery, ImageAsset, Preferences } from '$lib/types';

	const { t } = i18n;

	let {
		isExtractBusy = false,
		preferences
	}: { isExtractBusy?: boolean; preferences: Preferences } = $props();

	let galleries = $derived(appStore.galleries);

	async function copyToClipboard(url: string) {
		await copyUrlToClipboard(url, t);
	}

	async function copyAllLinks(gallery: GroupedGallery) {
		const links = gallery.images.map((img) => img.url).filter(Boolean);

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

	function exportTxtFor(gallery: GroupedGallery) {
		const txt = gallery.images
			.map((img) => img.url)
			.filter(Boolean)
			.join('\n');

		if (!txt) {
			toast.error(t('toast.nothingToExport'));

			return;
		}

		downloadTextFile(
			`${safeFilename(gallery.title) || sourceHost(gallery.webpage_url) || 'gallery'}.txt`,
			txt
		);
		toast.success(t('toast.exported'));
	}

	function downloadImage(gallery: GroupedGallery, image: ImageAsset, index: number) {
		try {
			const base = safeFilename(gallery.title) || sourceHost(gallery.webpage_url) || 'image';
			const filename = `${base}-${index + 1}.${image.ext || 'jpg'}`;
			const link = document.createElement('a');

			link.href = image.url;
			link.download = filename;
			link.click();
			toast.success(t('toast.downloadStarted', { name: filename }));
		} catch {
			toast.error(t('toast.downloadFailed'));
		}
	}

	// Keyed by the gallery object itself -- same pattern VideoExtractList uses
	// for its per-group refresh spinner.
	const refreshTracker = new GroupRefreshTracker<GroupedGallery>();

	async function refreshGallery(gallery: GroupedGallery) {
		if (!gallery.webpage_url) {
			return;
		}

		await refreshTracker.run(gallery, async () => {
			const ok = await extraction.extractLinks(gallery.webpage_url!, { forceRefresh: true });

			if (ok) {
				appStore.removeGalleryExtractResultFromStore(gallery);
			}
		});
	}

	function removeGallery(gallery: GroupedGallery) {
		appStore.removeGalleryExtractResultFromStore(gallery);
		toast.info(t('toast.itemRemoved'));
	}

	// Large galleries (hundreds of images on some sites) shouldn't render an
	// unusably huge grid up front -- cap the initial render and let the user
	// expand explicitly.
	const INITIAL_VISIBLE = 16;
	const expandedGalleries = new SvelteMap<GroupedGallery, boolean>();

	function visibleImages(gallery: GroupedGallery): ImageAsset[] {
		if (expandedGalleries.get(gallery) || gallery.images.length <= INITIAL_VISIBLE) {
			return gallery.images;
		}

		return gallery.images.slice(0, INITIAL_VISIBLE);
	}

	function toggleExpanded(gallery: GroupedGallery) {
		expandedGalleries.set(gallery, !expandedGalleries.get(gallery));
	}

	// Free-text filter over title and source URL.
	let filterQuery = $state('');

	let filteredGalleries = $derived.by(() => {
		const q = filterQuery.trim().toLowerCase();

		if (!q) {
			return galleries;
		}

		return galleries.filter((g) =>
			[g.title ?? '', g.webpage_url ?? ''].join(' ').toLowerCase().includes(q)
		);
	});

	let totalImages = $derived(galleries.reduce((sum, g) => sum + g.images.length, 0));

	// Click-to-enlarge lightbox; also the one place "open original" lives.
	let lightboxGallery = $state<GroupedGallery | null>(null);
	let lightboxIndex = $state(0);
	let lightboxOpen = $state(false);

	let lightboxImage = $derived(lightboxGallery?.images[lightboxIndex] ?? null);

	function openLightbox(gallery: GroupedGallery, index: number) {
		lightboxGallery = gallery;
		lightboxIndex = index;
		lightboxOpen = true;
	}

	function stepLightbox(delta: number) {
		if (!lightboxGallery) {
			return;
		}

		const count = lightboxGallery.images.length;

		lightboxIndex = (lightboxIndex + delta + count) % count;
	}

	function onLightboxKeydown(event: KeyboardEvent) {
		if (event.key === 'ArrowLeft') {
			stepLightbox(-1);
		} else if (event.key === 'ArrowRight') {
			stepLightbox(1);
		}
	}
</script>

{#if galleries.length > 0}
	<div class="mb-10">
		<p class="sr-only" aria-live="polite" role="status">
			{t('gallery.resultCount', { n: totalImages })}
		</p>

		<div class="mb-4 flex flex-wrap items-center justify-between gap-3">
			<h2 class="flex items-center gap-2 text-lg font-bold tracking-tight">
				<ImagesIcon class="text-aurora-1 h-5 w-5" />
				{t('gallery.heading')}
				<span class="text-muted-foreground font-normal">({galleries.length})</span>
			</h2>
		</div>

		{#if galleries.length > 1}
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

		{#if filteredGalleries.length === 0}
			<p class="text-muted-foreground py-8 text-center text-sm">{t('extract.noMatches')}</p>
		{/if}

		<div
			class="grid gap-4 sm:gap-5 {preferences.layoutList === 'grid'
				? 'grid-cols-1 lg:grid-cols-2'
				: 'grid-cols-1'}"
		>
			{#each filteredGalleries as gallery (gallery)}
				<SourceGroupCard
					sourceUrl={gallery.webpage_url ?? ''}
					itemCount={gallery.images.length}
					onCopyAll={() => copyAllLinks(gallery)}
					onExportTxt={() => exportTxtFor(gallery)}
					onRefresh={() => refreshGallery(gallery)}
					refreshing={refreshTracker.isRefreshing(gallery)}
					onRemove={() => removeGallery(gallery)}
				>
					<div class="px-3.5 pt-1 sm:px-0">
						{#if gallery.skippedCount}
							<p class="text-muted-foreground mb-2 flex items-center gap-1.5 text-xs">
								<TriangleAlert class="h-3 w-3 shrink-0" />
								{t('gallery.someSkipped', { n: gallery.skippedCount })}
							</p>
						{/if}
						<!-- Responsive auto-fit grid: the column count adapts to how
						     many images there are (1 image fills the row, 2 share it
						     evenly, ...) instead of a fixed column count leaving empty
						     space or producing uneven rows. -->
						<div
							class="grid gap-2"
							style="grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));"
						>
							{#each visibleImages(gallery) as image, index (image.url)}
								<div class="group relative aspect-square overflow-hidden rounded-xl bg-muted">
									<button
										type="button"
										onclick={() => openLightbox(gallery, index)}
										class="absolute inset-0 cursor-zoom-in"
										aria-label={t('gallery.imageAlt', { n: index + 1 })}
									>
										<img
											src={image.url}
											alt={t('gallery.imageAlt', { n: index + 1 })}
											loading="lazy"
											decoding="async"
											class="h-full w-full object-cover transition-transform duration-200 group-hover:scale-105"
										/>
									</button>
									<button
										type="button"
										onclick={() => downloadImage(gallery, image, index)}
										title={t('gallery.downloadImage')}
										aria-label={t('gallery.downloadImage')}
										class="bg-black/50 text-white hover:bg-black/70 absolute bottom-1.5 inset-e-1.5 z-10 flex h-7 w-7 cursor-pointer items-center justify-center rounded-full backdrop-blur-sm transition-colors"
									>
										<Download class="h-3.5 w-3.5" />
									</button>
								</div>
							{/each}
						</div>

						{#if gallery.images.length > INITIAL_VISIBLE}
							<Button
								variant="outline"
								size="sm"
								onclick={() => toggleExpanded(gallery)}
								class="mt-3 w-full cursor-pointer rounded-full text-xs"
							>
								{expandedGalleries.get(gallery)
									? t('gallery.showLess')
									: t('gallery.showAll', { n: gallery.images.length })}
							</Button>
						{/if}
					</div>
				</SourceGroupCard>
			{/each}
		</div>
	</div>
{/if}

<!-- Loading skeleton -- mirrors the real card shell + auto-fit grid shape,
     same spirit as VideoExtractList's skeleton. -->
{#if isExtractBusy}
	<section class="mb-10" role="status" aria-busy="true" aria-label={t('gallery.loading')}>
		<span class="sr-only">{t('gallery.loading')}</span>

		<div
			class="grid gap-4 sm:gap-5 {preferences.layoutList === 'grid'
				? 'grid-cols-1 lg:grid-cols-2'
				: 'grid-cols-1'}"
		>
			{#each [0, 1] as i (i)}
				<div
					class="border-border/60 bg-card/60 shadow-soft overflow-hidden rounded-2xl border py-3.5 sm:p-4"
				>
					<div
						class="border-border/40 mb-3 flex flex-wrap items-center gap-2 border-b px-3.5 pb-2.5 sm:px-0"
					>
						<div class="bg-muted h-3.5 w-3.5 shrink-0 animate-pulse rounded-full"></div>
						<div class="bg-muted h-3.5 w-40 max-w-full animate-pulse rounded"></div>
						<div class="ms-auto flex shrink-0 items-center gap-1.5">
							{#each [0, 1, 2, 3] as j (j)}
								<div class="bg-muted h-7 w-7 animate-pulse rounded-full"></div>
							{/each}
						</div>
					</div>

					<div class="px-3.5 sm:px-0">
						<div
							class="grid gap-2"
							style="grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));"
						>
							{#each [0, 1, 2, 3, 4, 5] as k (k)}
								<div class="bg-muted aspect-square animate-pulse rounded-xl"></div>
							{/each}
						</div>
					</div>
				</div>
			{/each}
		</div>
	</section>
{/if}

<!-- Lightbox: click-to-enlarge with prev/next through the same gallery. -->
<Dialog.Root bind:open={lightboxOpen}>
	<Dialog.Content
		onkeydown={onLightboxKeydown}
		class="bg-black/95 border-none max-w-[95vw] gap-0 p-0 sm:max-w-4xl"
		closeLabel={t('common.close')}
		showCloseButton
	>
		{#if lightboxImage && lightboxGallery}
			<div class="relative flex items-center justify-center">
				<img
					src={lightboxImage.url}
					alt={t('gallery.imageAlt', { n: lightboxIndex + 1 })}
					class="max-h-[80vh] w-auto max-w-full rounded-lg object-contain"
				/>

				{#if lightboxGallery.images.length > 1}
					<button
						type="button"
						onclick={() => stepLightbox(-1)}
						aria-label={t('gallery.prevImage')}
						class="bg-black/50 text-white hover:bg-black/70 absolute inset-s-2 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full backdrop-blur-sm transition-colors"
					>
						<ChevronLeft class="h-5 w-5" />
					</button>
					<button
						type="button"
						onclick={() => stepLightbox(1)}
						aria-label={t('gallery.nextImage')}
						class="bg-black/50 text-white hover:bg-black/70 absolute inset-e-2 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full backdrop-blur-sm transition-colors"
					>
						<ChevronRight class="h-5 w-5" />
					</button>
					<span
						class="bg-black/50 text-white absolute top-2 inset-s-2 rounded-full px-2 py-0.5 text-xs font-medium backdrop-blur-sm"
					>
						{lightboxIndex + 1} / {lightboxGallery.images.length}
					</span>
				{/if}

				<div class="absolute bottom-2 inset-x-0 flex items-center justify-center gap-2">
					<Button
						variant="secondary"
						size="sm"
						onclick={() => copyToClipboard(lightboxImage?.url ?? '')}
						class="gap-1.5 rounded-full text-xs"
					>
						<Copy class="h-3.5 w-3.5" />
						{t('gallery.copyImageUrl')}
					</Button>
					<Button
						variant="secondary"
						size="sm"
						onclick={() =>
							lightboxImage && downloadImage(lightboxGallery!, lightboxImage, lightboxIndex)}
						class="gap-1.5 rounded-full text-xs"
					>
						<Download class="h-3.5 w-3.5" />
						{t('gallery.downloadImage')}
					</Button>
					<!-- eslint-disable svelte/no-navigation-without-resolve -->
					<a
						href={lightboxImage.sourceUrl || lightboxImage.url}
						target="_blank"
						rel="noreferrer noopener"
						class="bg-secondary text-secondary-foreground hover:bg-secondary/80 inline-flex h-8 items-center gap-1.5 rounded-full px-3 text-xs font-medium transition-colors"
					>
						<ExternalLink class="h-3.5 w-3.5" />
						{t('gallery.openOriginal')}
					</a>
					<!-- eslint-enable svelte/no-navigation-without-resolve -->
				</div>
			</div>
		{/if}
	</Dialog.Content>
</Dialog.Root>
