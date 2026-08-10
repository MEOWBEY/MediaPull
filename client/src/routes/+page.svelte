<script lang="ts">
	import { onMount } from 'svelte';

	import ErrorAlert from '$lib/components/ErrorAlert.svelte';
	import GalleryExtractList from '$lib/components/GalleryExtractList.svelte';
	import InputUrl from '$lib/components/InputUrl.svelte';
	import Instructions from '$lib/components/Instructions.svelte';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import MediaCard from '$lib/components/MediaCard.svelte';
	import PreferencesDialog from '$lib/components/PreferencesDialog.svelte';
	import VideoExtractList from '$lib/components/VideoExtractList.svelte';
	import { extraction } from '$lib/extraction.svelte';
	import { i18n } from '$lib/i18n/index.svelte';
	import { appStore } from '$lib/stores/app-state.svelte';
	import { health } from '$lib/stores/health.svelte';
	import { localFiles } from '$lib/stores/local-library.svelte';
	import { ui } from '$lib/stores/ui.svelte';

	const { t } = i18n;

	let isVideoExtractRunning = $derived(appStore.isVideoExtractRunning);

	let preferences = $derived(appStore.preferences);
	let videoExtractError = $derived(appStore.videoExtractError);

	let hasResults = $derived(
		appStore.videoExtractResults.length > 0 || appStore.galleries.length > 0
	);
	const runVideoExtractFromServer = (url: string) => extraction.extract(url);
	const cancelActiveOperation = () => extraction.cancel();

	let batchTotal = $derived(extraction.batchTotal);
	let batchDone = $derived(extraction.batchDone);

	let isExtractBusy = $derived(isVideoExtractRunning || batchTotal > 0);

	// ----- Local files -----------------------------------------------
	// The whole local-file library (entries, persisted subtitles, audio
	// splits, IndexedDB round-trip) lives in `localFiles` — the page only
	// drops files in and renders the store's entries; see
	// `$lib/stores/local-library.svelte.ts`.
	let showEmptyState = $derived(
		!hasResults && !isExtractBusy && !videoExtractError && localFiles.entries.length === 0
	);
	let showSkeleton = $derived(isExtractBusy && !hasResults);

	// ----- Global drop zone ------------------------------------------
	let isDraggingOver = $state(false);
	let dragCounter = $state(0);

	function onDragEnter(e: DragEvent) {
		if (!health.localFilesEnabled) {
			return;
		}
		const hasFile = e.dataTransfer?.types.includes('Files');

		if (!hasFile) {
			return;
		}
		e.preventDefault();
		dragCounter++;
		isDraggingOver = true;
	}

	function onDragLeave() {
		if (!health.localFilesEnabled) {
			return;
		}
		dragCounter--;
		if (dragCounter <= 0) {
			dragCounter = 0;
			isDraggingOver = false;
		}
	}

	function onDragOver(e: DragEvent) {
		if (!health.localFilesEnabled) {
			return;
		}
		e.preventDefault();
	}

	function onDrop(e: DragEvent) {
		if (!health.localFilesEnabled) {
			return;
		}
		e.preventDefault();
		dragCounter = 0;
		isDraggingOver = false;
		const files = Array.from(e.dataTransfer?.files ?? []);

		files.forEach((file) => localFiles.add(file));
	}

	// Scroll to and focus the URL field.
	function focusInput(scroll = true) {
		const el = document.getElementById('video-url') as HTMLInputElement | null;

		if (!el) {
			return;
		}
		if (scroll) {
			el.scrollIntoView({ behavior: 'smooth', block: 'center' });
		}
		el.focus({ preventScroll: scroll });
	}

	onMount(() => {
		void health.load();

		const isDesktop = window.matchMedia('(pointer: fine)').matches;

		if (isDesktop || !hasResults) {
			focusInput(false);
		}

		void appStore.remintLibraryProxyTokens();
		void localFiles.restore();
	});
</script>

<svelte:head>
	<title>MediaPull — {i18n.t('app.tagline')}</title>
	<meta
		name="description"
		content="Paste a URL to extract downloadable video formats or image galleries. Built-in player, optional subtitles, cookies for signed-in sites, and proxy when direct play fails."
	/>
</svelte:head>

<!-- Global drop zone: listens on the whole page -->
<svelte:window
	ondragenter={onDragEnter}
	ondragleave={onDragLeave}
	ondragover={onDragOver}
	ondrop={onDrop}
/>

{#if isDraggingOver}
	<div
		class="pointer-events-none fixed inset-0 z-50 flex items-center justify-center"
		aria-hidden="true"
	>
		<div
			class="bg-background/80 border-signal absolute inset-4 rounded-xl border-2 border-dashed backdrop-blur-sm"
		></div>
		<span class="text-signal relative z-10 font-mono text-lg font-semibold">
			{t('localFile.dropAnywhere')}
		</span>
	</div>
{/if}

<div class="w-full">
	<section class="relative mx-auto w-full max-w-7xl px-2 pt-12 pb-8 sm:px-4 sm:pt-20">
		<h1 class="font-heading max-w-3xl text-4xl font-bold tracking-tight text-balance sm:text-6xl">
			{t('hero.titleLead')}
			<br />
			<span class="ds-gradient-text">{t('hero.titleHighlight')}</span>
			{#if t('hero.titleTrail')}
				{t('hero.titleTrail')}
			{/if}
		</h1>

		<div class="mt-8 w-full">
			<InputUrl
				{runVideoExtractFromServer}
				{cancelActiveOperation}
				{isVideoExtractRunning}
				{batchTotal}
				{batchDone}
				onLocalFile={health.localFilesEnabled ? (file: File) => localFiles.add(file) : undefined}
			/>
		</div>
	</section>

	<div class="mx-auto w-full max-w-7xl px-2 pb-2 sm:px-4">
		{#if videoExtractError}
			<ErrorAlert {videoExtractError} onOpenCookies={() => ui.openPreferences('cookies')} />
		{/if}

		<!-- Local file cards appear above URL-extracted results -->
		{#if localFiles.entries.length > 0}
			<div class="mb-2">
				{#each localFiles.entries as entry, i (entry.id)}
					<MediaCard {entry} {preferences} isFirst={i === 0} />
				{/each}
			</div>
		{/if}

		<VideoExtractList {preferences} />

		<GalleryExtractList {preferences} />

		{#if showSkeleton}
			<LoadingSkeleton {preferences} />
		{/if}

		{#if showEmptyState}
			<div
				class="border-border text-muted-foreground my-6 flex w-full flex-col items-start rounded-lg border border-dashed px-6 py-10 text-start sm:py-12"
			>
				<h2 class="font-heading text-xl font-bold tracking-tight sm:text-2xl">
					{t('empty.title')}
				</h2>
				<p class="text-muted-foreground mt-2 max-w-md text-sm leading-relaxed">
					{t('empty.body')}
				</p>
			</div>
		{/if}

		{#if !hasResults && localFiles.entries.length === 0}
			<Instructions />
		{/if}
	</div>
</div>

<PreferencesDialog {preferences} bind:isPreferencesDialogOpen={ui.preferencesOpen} />
