<script lang="ts">
	import ChevronLeft from '@lucide/svelte/icons/chevron-left';
	import ChevronRight from '@lucide/svelte/icons/chevron-right';
	import Copy from '@lucide/svelte/icons/copy';
	import Download from '@lucide/svelte/icons/download';
	import ExternalLink from '@lucide/svelte/icons/external-link';
	import ImagesIcon from '@lucide/svelte/icons/images';
	import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
	import { SvelteMap } from 'svelte/reactivity';
	import { toast } from 'svelte-sonner';

	import { copyUrlToClipboard } from '$lib/clipboard';
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

	let { preferences }: { preferences: Preferences } = $props();

	let galleries = $derived(appStore.galleries);

	async function copyToClipboard(url: string) {
		await copyUrlToClipboard(url, t);
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

	const bulkDownloading = new SvelteMap<GroupedGallery, boolean>();

	/** Sequential bulk download (no zip dep) — fetches each proxied image and
	 *  triggers a save. Concurrency 1 keeps browsers from choking. */
	async function downloadAll(gallery: GroupedGallery) {
		if (bulkDownloading.get(gallery) || !gallery.images.length) {
			return;
		}
		bulkDownloading.set(gallery, true);
		const base = safeFilename(gallery.title) || sourceHost(gallery.webpage_url) || 'image';
		let done = 0;
		let failed = 0;
		const total = gallery.images.length;
		const toastId = toast.loading(t('gallery.downloadingAll', { done: 0, total }));

		try {
			for (let i = 0; i < gallery.images.length; i++) {
				const image = gallery.images[i];

				try {
					const res = await fetch(image.url);

					if (!res.ok) {
						throw new Error(String(res.status));
					}
					const blob = await res.blob();
					const objectUrl = URL.createObjectURL(blob);
					const link = document.createElement('a');

					link.href = objectUrl;
					link.download = `${base}-${i + 1}.${image.ext || 'jpg'}`;
					link.click();
					URL.revokeObjectURL(objectUrl);
					done += 1;
				} catch {
					failed += 1;
				}
				toast.loading(t('gallery.downloadingAll', { done: done + failed, total }), {
					id: toastId
				});
				// Brief pause so the browser doesn't coalesce download prompts.
				await new Promise((r) => setTimeout(r, 120));
			}
			if (failed === 0) {
				toast.success(t('gallery.downloadAllDone', { n: done }), { id: toastId });
			} else {
				toast.warning(t('gallery.downloadAllPartial', { done, total }), { id: toastId });
			}
		} finally {
			bulkDownloading.set(gallery, false);
		}
	}

	function warningLabel(code: string, message: string): string {
		if (code === 'login') {
			return t('gallery.warning.login');
		}
		if (code === 'rate_limit') {
			return t('gallery.warning.rateLimit');
		}
		if (code === 'quality') {
			return t('gallery.warning.quality');
		}
		if (code === 'truncated') {
			return t('gallery.warning.truncated');
		}

		return t('gallery.warning.generic', { message });
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

		<div
			class="grid gap-4 sm:gap-5 {preferences.layoutList === 'grid'
				? 'grid-cols-1 lg:grid-cols-2'
				: 'grid-cols-1'}"
		>
			{#each galleries as gallery (gallery)}
				<SourceGroupCard
					sourceUrl={gallery.webpage_url ?? ''}
					itemCount={gallery.images.length}
					onCopyUrl={gallery.webpage_url
						? () => copyToClipboard(gallery.webpage_url ?? '')
						: undefined}
					onExportTxt={() => exportTxtFor(gallery)}
					showExports={preferences.showExportButtons}
					onRefresh={() => refreshGallery(gallery)}
					refreshing={refreshTracker.isRefreshing(gallery)}
					onRemove={() => removeGallery(gallery)}
				>
					<div class="px-3.5 pt-1 sm:px-0">
						{#if gallery.images.length > 1}
							<div class="mb-2 flex flex-wrap items-center gap-2">
								<Button
									variant="outline"
									size="sm"
									class="h-7 gap-1.5 rounded-full text-xs"
									disabled={bulkDownloading.get(gallery)}
									onclick={() => downloadAll(gallery)}
								>
									<Download class="h-3 w-3" />
									{t('gallery.downloadAll')}
								</Button>
							</div>
						{/if}
						{#if gallery.skippedCount}
							<p class="text-muted-foreground mb-2 flex items-center gap-1.5 text-xs">
								<TriangleAlert class="h-3 w-3 shrink-0" />
								{t('gallery.someSkipped', { n: gallery.skippedCount })}
							</p>
						{/if}
						{#each gallery.warnings ?? [] as warning (warning.code + warning.message)}
							<p class="text-muted-foreground mb-1.5 flex items-center gap-1.5 text-xs">
								<TriangleAlert class="h-3 w-3 shrink-0" />
								{warningLabel(warning.code, warning.message)}
							</p>
						{/each}
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
											class="h-full w-full object-cover"
										/>
									</button>
									<button
										type="button"
										onclick={() => downloadImage(gallery, image, index)}
										title={t('gallery.downloadImage')}
										aria-label={t('gallery.downloadImage')}
										class="bg-black/60 text-white hover:bg-black/80 absolute bottom-1.5 inset-e-1.5 z-10 flex h-7 items-center gap-1 rounded-full px-2.5 text-xs font-medium backdrop-blur-sm transition-colors"
									>
										<Download class="h-3.5 w-3.5" />
										<span>{t('extract.download')}</span>
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
