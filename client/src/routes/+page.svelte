<script lang="ts">
	import { onMount } from 'svelte';

	import ErrorAlert from '$lib/components/ErrorAlert.svelte';
	import GalleryExtractList from '$lib/components/GalleryExtractList.svelte';
	import InputUrl from '$lib/components/InputUrl.svelte';
	import Instructions from '$lib/components/Instructions.svelte';
	import LoadingSkeleton from '$lib/components/LoadingSkeleton.svelte';
	import PreferencesDialog from '$lib/components/PreferencesDialog.svelte';
	import VideoExtractList from '$lib/components/VideoExtractList.svelte';
	import { extraction } from '$lib/extraction.svelte';
	import { i18n } from '$lib/i18n/index.svelte';
	import { appStore } from '$lib/stores/app-state.svelte';
	import { ui } from '$lib/stores/ui.svelte';

	const {t} = i18n;

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

	// Stays true across a whole batch (batchTotal > 0) so the skeleton doesn't
	// flicker off between individual items in the queue.
	let isExtractBusy = $derived(isVideoExtractRunning || batchTotal > 0);

	let showEmptyState = $derived(!hasResults && !isExtractBusy && !videoExtractError);
	// One neutral skeleton, shown only while extracting into an EMPTY library.
	// Once any result (video or gallery) is on screen we don't cover it with a
	// skeleton, and we never show a video- AND gallery-shaped skeleton at once
	// -- a single generic placeholder stands in until the real kind lands.
	let showSkeleton = $derived(isExtractBusy && !hasResults);

	// Scroll to and focus the URL field — used by the side button and on first load.
	function focusInput(scroll = true) {
		const el = document.getElementById('video-url') as HTMLInputElement | null;

		if (!el) {return;}
		if (scroll) {el.scrollIntoView({ behavior: 'smooth', block: 'center' });}
		el.focus({ preventScroll: scroll });
	}

	onMount(() => {
		// Most visits start by pasting a URL, so focus the field on load. Limit it
		// to pointer (desktop) devices — auto-focusing on touch pops the on-screen
		// keyboard, which is jarring.
		const isDesktop = window.matchMedia('(pointer: fine)').matches;

		if (isDesktop || !hasResults) {focusInput(false);}

		// Library proxy URLs embed short-lived ctok values — refresh them when
		// the user still has cookies for those hosts.
		void appStore.remintLibraryProxyTokens();
	});

	$effect(() => {
		if (typeof document === 'undefined' || !preferences) {return;}

		const { theme } = preferences;
		const media = window.matchMedia('(prefers-color-scheme: dark)');

		// Apply the `dark` class ourselves so 'system' tracks the OS. This only
		// writes to the DOM (no reactive state), so it can't loop the effect.
		const applyTheme = () => {
			const dark = theme === 'dark' || (theme === 'system' && media.matches);

			document.documentElement.classList.toggle('dark', dark);
		};

		applyTheme();

		// Only follow live OS changes while on 'system'.
		if (theme === 'system') {
			media.addEventListener('change', applyTheme);

			return () => media.removeEventListener('change', applyTheme);
		}
	});
</script>

<svelte:head>
	<title>MediaPull — Paste a link. Pull the media.</title>
	<meta
		name="description"
		content="Paste a URL to extract downloadable video formats or image galleries. Built-in player, optional subtitles, cookies for signed-in sites, and proxy when direct play fails."
	/>
</svelte:head>

<div class="w-full">
	<section class="relative mx-auto w-full max-w-7xl px-2 pt-12 pb-8 sm:px-4 sm:pt-20">
		<h1
			class="font-heading max-w-3xl text-4xl font-bold tracking-tight text-balance sm:text-6xl"
		>
			{t('hero.titleLead')}
			<br />
			<span class="ds-gradient-text">{t('hero.titleHighlight')}</span>
			{#if t('hero.titleTrail')}
				{t('hero.titleTrail')}
			{/if}
		</h1>

		<!-- Input spans the full row width. -->
		<div class="mt-8 w-full">
			<InputUrl
				{runVideoExtractFromServer}
				{cancelActiveOperation}
				{isVideoExtractRunning}
				{batchTotal}
				{batchDone}
			/>
		</div>
	</section>

	<!-- Narrower side padding on phones so previews use more width. -->
	<div class="mx-auto w-full max-w-7xl px-2 pb-2 sm:px-4">
		{#if videoExtractError}
			<ErrorAlert {videoExtractError} onOpenCookies={() => ui.openPreferences('cookies')} />
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

		{#if !hasResults}
			<!-- The guide only shows before the first result. Once the user has
			     extracted something they've clearly learned the flow, so it's
			     dropped entirely rather than kept as a collapsed disclosure. -->
			<Instructions />
		{/if}
	</div>
</div>

<PreferencesDialog {preferences} bind:isPreferencesDialogOpen={ui.preferencesOpen} />
