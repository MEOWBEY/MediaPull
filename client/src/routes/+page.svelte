<script lang="ts">
	import { toast } from 'svelte-sonner';
	import OperationStatusBar from '$lib/components/OperationStatusBar.svelte';
	import InputUrl from '$lib/components/InputUrl.svelte';
	import ErrorAlert from '$lib/components/ErrorAlert.svelte';
	import OvcProxyList from '$lib/components/OvcProxyList.svelte';
	import VideoExtractList from '$lib/components/VideoExtractList.svelte';
	import Instructions from '$lib/components/Instructions.svelte';
	import PreferencesDialog from '$lib/components/PreferencesDialog.svelte';

	import { appStore } from '$lib/stores/app-state.svelte';

	let isPreferencesDialogOpen = $state(false);
	let elapsedOperationSeconds = $state(0);
	let operationTimerInterval: NodeJS.Timeout | null = null;

	// abort controller for operations
	let activeOperationController: AbortController | null = null;

	let isVideoExtractRunning = $derived(appStore.isVideoExtractRunning);
	let isOVCProxyRunning = $derived(appStore.isOVCProxyRunning);

	let preferences = $derived(appStore.preferences);
	let ovcProxyError = $derived(appStore.ovcProxyError);
	let videoExtractError = $derived(appStore.videoExtractError);
	function startOperation(): void {
		activeOperationController = new AbortController();

		// start timer
		elapsedOperationSeconds = 0;
		operationTimerInterval = setInterval(() => elapsedOperationSeconds++, 1000);
	}

	function stopOperation(): void {
		if (activeOperationController) {
			activeOperationController.abort();
			activeOperationController = null;
		}

		// stop timer
		if (operationTimerInterval) {
			clearInterval(operationTimerInterval);
			operationTimerInterval = null;
		}
	}

	function validateUrl(url: string): boolean {
		if (!url?.trim()) {
			toast.error('Please enter a valid URL');
			return false;
		}

		try {
			new URL(url);
			return true;
		} catch {
			toast.error('Invalid URL format');
			return false;
		}
	}

	async function runVideoExtractFromServer(url) {
		const inputUrl = url?.trim();
		if (!validateUrl(inputUrl)) return;

		startOperation();
		appStore.isVideoExtractRunning = true;
		appStore.videoExtractError = null;

		try {
			const response = await fetch('/api/extract-videos', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ url: inputUrl }),
				signal: activeOperationController?.signal
			});

			const data = await response.json();

			if (!data.success) {
				throw new Error(data.error || 'Operation failed');
			}

			if (activeOperationController?.signal.aborted) return;

			appStore.addVideoExtractResultsToStore(data.video);

			toast.success(`Extracted ${data.video.formats?.length} formats`);
		} catch (error: unknown) {
			if (error instanceof Error && error.name === 'AbortError') return;

			const errorMessage = error instanceof Error ? error.message : 'Unknown error occurred';
			appStore.videoExtractError = errorMessage;
			toast.error(`Error: ${errorMessage}`);
		} finally {
			appStore.isVideoExtractRunning = false;
			stopOperation();
		}
	}

	async function runOvcProxyFromServer(url) {
		const inputUrl = url?.trim();
		if (!validateUrl(inputUrl)) return;

		startOperation();
		appStore.isOVCProxyRunning = true;
		appStore.videoExtractError = null;

		try {
			const response = await fetch('/api/ovc-proxy-video', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ url: inputUrl }),
				signal: activeOperationController?.signal
			});

			const data = await response.json();

			if (!data.success) {
				throw new Error(data.error || 'Operation failed');
			}

			if (activeOperationController?.signal.aborted) return;

			appStore.addOvcProxyResultsToStore(data.video);
			toast.success('Ovc proxy completed');
		} catch (error: unknown) {
			if (error instanceof Error && error.name === 'AbortError') return;

			const errorMessage = error instanceof Error ? error.message : 'Unknown error occurred';
			appStore.videoExtractError = errorMessage;
			toast.error(`Error: ${errorMessage}`);
		} finally {
			appStore.isOVCProxyRunning = false;
			stopOperation();
		}
	}

	function cancelActiveOperation(): void {
		stopOperation();
		appStore.isOVCProxyRunning = false;
		appStore.isVideoExtractRunning = false;
		toast.info('Operation cancelled');
	}

	$effect(() => {
		if (typeof document === 'undefined' || !preferences) return;

		const root = document.documentElement;

		// Apply all preferences
		root.classList.toggle('dark', preferences.theme === 'dark');
		root.classList.toggle('high-contrast', preferences.enableHighContrast);
		root.classList.toggle('compact-mode', preferences.enableCompact);
		root.classList.toggle('no-animations', !preferences.enableAnimations);
	});
</script>

<svelte:head>
	<title>Video Extractor - Video Processing</title>
	<meta name="description" content="Extract and process videos from URLs efficiently" />
</svelte:head>

<div class={preferences.enableCompact ? 'compact-mode' : ''}>
	<div class="container mx-auto px-4 py-6">
		<OperationStatusBar
			{elapsedOperationSeconds}
			{isVideoExtractRunning}
			{isOVCProxyRunning}
			{videoExtractError}
			{ovcProxyError}
			bind:isPreferencesDialogOpen
		/>

		<InputUrl
			{runVideoExtractFromServer}
			{runOvcProxyFromServer}
			{cancelActiveOperation}
			{isVideoExtractRunning}
			{isOVCProxyRunning}
			{preferences}
		/>

		{#if videoExtractError || ovcProxyError}
			<ErrorAlert {videoExtractError} {ovcProxyError} />
		{/if}

		<OvcProxyList {preferences} />
		<VideoExtractList
			{isVideoExtractRunning}
			{isOVCProxyRunning}
			{preferences}
			{runOvcProxyFromServer}
		/>
		<Instructions {preferences} />
	</div>
</div>

<PreferencesDialog {preferences} bind:isPreferencesDialogOpen />

<style>
	:global(.compact-mode) {
		--spacing-unit: 0.5rem;
	}

	:global(.high-contrast) {
		--border-width: 2px;
		filter: contrast(1.2);
	}

	:global(.no-animations) * {
		animation-duration: 0.01ms !important;
		animation-iteration-count: 1 !important;
		transition-duration: 0.01ms !important;
	}
</style>
