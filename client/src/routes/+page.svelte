<script lang="ts">
	import ArrowUp from '@lucide/svelte/icons/arrow-up';
	import Clapperboard from '@lucide/svelte/icons/clapperboard';
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

	const {t} = i18n;

	let isPreferencesDialogOpen = $state(false);

	let elapsedOperationSeconds = $derived(extraction.elapsedSeconds);
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
		document.documentElement.classList.toggle('no-animations', !preferences.enableAnimations);

		// Only follow live OS changes while on 'system'.
		if (theme === 'system') {
			media.addEventListener('change', applyTheme);

			return () => media.removeEventListener('change', applyTheme);
		}
	});
</script>

<svelte:head>
	<title>Pullbox — Extract direct video links from any page</title>
	<meta
		name="description"
		content="Paste a webpage URL to extract direct video links via yt-dlp and HTML scraping, then preview with the built-in player, download, or stream through an optional proxy."
	/>
</svelte:head>

<div class="w-full">
	<!-- ===== Hero / command deck ===== -->
	<section class="relative mx-auto w-full max-w-3xl px-4 pt-12 pb-8 text-center sm:pt-20">
		<h1 class="font-heading text-3xl font-extrabold tracking-tight text-balance sm:text-6xl">
			{t('hero.titleLead')}
			<span class="ds-gradient-text">{t('hero.titleHighlight')}</span><br class="hidden sm:block" />
			{t('hero.titleTrail')}
		</h1>
		<!-- <p class="text-muted-foreground mx-auto mt-4 max-w-xl text-sm text-pretty sm:text-lg">
			{t('hero.subtitle')}
		</p> -->

		<div class="mt-8">
			<InputUrl
				{runVideoExtractFromServer}
				{cancelActiveOperation}
				{isVideoExtractRunning}
				{elapsedOperationSeconds}
				{batchTotal}
				{batchDone}
				bind:isPreferencesDialogOpen
			/>
		</div>
	</section>

	<!-- ===== Workspace ===== -->
	<!-- Tighter side padding on phones so the video previews get more width. -->
	<div class="container mx-auto max-w-6xl px-2 pb-12 sm:px-4">
		{#if videoExtractError}
			<ErrorAlert {videoExtractError} />
		{/if}

		<VideoExtractList {preferences} />

		<GalleryExtractList {preferences} />

		{#if showSkeleton}
			<LoadingSkeleton {preferences} />
		{/if}

		{#if showEmptyState}
			<div
				class="border-border/60 my-10 flex w-full flex-col items-center rounded-[2.5rem] border-2 border-dashed px-6 py-20 text-center sm:py-28"
			>
				<span
					class="ds-breathe bg-primary/10 text-primary mb-6 flex h-24 w-24 items-center justify-center rounded-full"
				>
					<Clapperboard class="h-11 w-11" />
				</span>
				<h2 class="text-2xl font-bold tracking-tight sm:text-3xl">{t('empty.title')}</h2>
				<p class="text-muted-foreground mt-3 max-w-md text-sm leading-relaxed sm:text-base">
					{t('empty.body')}
				</p>
			</div>
		{/if}

		<Instructions {preferences} />
	</div>
</div>

<PreferencesDialog {preferences} bind:isPreferencesDialogOpen />

<!-- Quick jump back to the URL field once results have pushed it off-screen. -->
{#if hasResults}
	<button
		type="button"
		onclick={() => focusInput()}
		title={t('input.jumpToInput')}
		aria-label={t('input.jumpToInput')}
		class="ds-glass shadow-float text-primary hover:bg-primary hover:text-primary-foreground fixed inset-e-5 bottom-5 z-40 hidden h-12 w-12 items-center justify-center rounded-full transition-colors sm:flex"
	>
		<ArrowUp class="h-5 w-5" />
	</button>
{/if}

<style>
	:global(.no-animations) * {
		animation-duration: 0.01ms !important;
		animation-iteration-count: 1 !important;
		transition-duration: 0.01ms !important;
	}

	/* Gentle idle "breathing" for the empty-state icon blob — signals waiting/active,
	   not broken. Slow and low-delta to stay calm. */
	.ds-breathe {
		animation: ds-breathe 4s ease-in-out infinite;
	}
	@keyframes ds-breathe {
		0%,
		100% {
			transform: scale(1);
			opacity: 0.9;
		}
		50% {
			transform: scale(1.06);
			opacity: 1;
		}
	}
</style>
