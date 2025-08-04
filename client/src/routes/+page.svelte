<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { toast } from 'svelte-sonner';

	// Components
	import StatusBar from '$lib/components/StatusBar.svelte';
	import VideoInput from '$lib/components/VideoInput.svelte';
	import ErrorAlert from '$lib/components/ErrorAlert.svelte';
	import ProcessedVideos from '$lib/components/ProcessedVideos.svelte';
	import ExtractedVideos from '$lib/components/ExtractedVideos.svelte';
	import Instructions from '$lib/components/Instructions.svelte';
	import PreferencesDialog from '$lib/components/PreferencesDialog.svelte';

	// Store and utilities
	import { videoStore, apiCache } from '$lib/stores/app-state.svelte';
	import { keyboardShortcuts } from '$lib/utils/keyboard';
	import { themeManager } from '$lib/utils/theme';
	import { videoProcessor } from '$lib/utils/video-processor';

	let showPreferences = $state(false);
	let operationTimer = $state(0);
	let timerInterval: NodeJS.Timeout | null = null;
	let abortController: AbortController | null = null;

	let isOperationRunning = $derived(videoStore.processing || videoStore.extracting);
	let preferences = $derived(videoStore.preferences);
	let hasErrors = $derived(Boolean(videoStore.processingError || videoStore.extractionError));

	// Apply theme effects
	$effect(() => {
		themeManager.applyTheme(preferences);
	});

	// Timer management
	$effect(() => {
		if (isOperationRunning && !timerInterval) startTimer();
		else if (!isOperationRunning && timerInterval) stopTimer();
	});

	// Lifecycle
	onMount(() => {
		if (isOperationRunning) startTimer();
		keyboardShortcuts.setup(preferences, {
			onExtract: handleExtractVideos,
			onCancel: handleCancelOperation,
			onTogglePreferences: () => (showPreferences = !showPreferences)
		});
		autoCleanCache();

		// Setup auto-clean interval
		const interval = setInterval(autoCleanCache, 5 * 60 * 1000);
		return () => clearInterval(interval);
	});

	onDestroy(() => {
		stopTimer();
		if (abortController) abortController.abort();
		keyboardShortcuts.cleanup();
	});

	// Timer functions
	function startTimer() {
		operationTimer = 0;
		timerInterval = setInterval(() => operationTimer++, 1000);
	}

	function stopTimer() {
		if (timerInterval) {
			clearInterval(timerInterval);
			timerInterval = null;
		}
	}

	// Main operations
	async function handleExtractVideos() {
		const inputUrl = videoStore.inputUrl;
		if (!inputUrl.trim()) {
			toast.error('Please enter a valid URL');
			return;
		}

		const result = await videoProcessor.extractVideos(inputUrl, {
			useCache: preferences.cacheEnabled,
			abortController: (abortController = new AbortController())
		});

		if (result.success) {
			toast.success(`Extracted ${result?.data?.totalFormats} formats`);
		} else if (result.error && !result.cancelled) {
			toast.error(`Error: ${result.error}`);
		}

		abortController = null;
	}

	async function handleProcessVideo(video?: any) {
		const result = await videoProcessor.processVideo(
			video || { originalUrl: videoStore.inputUrl },
			{
				abortController: video ? null : (abortController = new AbortController())
			}
		);

		if (result.success) {
			toast.success(`Processed in ${result?.data?.processingTime}ms`, {
				action: {
					label: 'Download',
					onClick: () => window.open(result?.data?.downloadUrl, '_blank')
				}
			});
		} else if (result.error && !result.cancelled) {
			toast.error(`Error: ${result.error}`);
		}

		if (!video) abortController = null;
	}

	function handleCancelOperation() {
		if (abortController) {
			abortController.abort();
			toast.info('Operation cancelled');
		}
		videoStore.processing = false;
		videoStore.extracting = false;
		videoStore.processingQueue.clear();
	}

	function autoCleanCache() {
		if (preferences.autoClearCache) {
			const stats = apiCache.getStats();
			if (stats.size > 50) {
				apiCache.clear();
				toast.info('Auto-cleared cache (50+ items)');
			}
		}
	}
</script>

<svelte:head>
	<title>DirectLinker - Video Processing</title>
	<meta name="description" content="Extract and process videos from URLs efficiently" />
</svelte:head>

<div class=" {preferences.compactMode ? 'compact-mode' : ''}">
	<div class="container mx-auto px-4 py-6">
		<!-- Status Bar -->
		<StatusBar {operationTimer} {isOperationRunning} bind:showPreferences />

		<!-- Main Input -->
		<VideoInput
			{handleExtractVideos}
			{handleProcessVideo}
			{handleCancelOperation}
			{isOperationRunning}
		/>

		<!-- Errors -->
		{#if hasErrors}
			<ErrorAlert />
		{/if}

		<!-- Processed Videos -->
		<ProcessedVideos />

		<!-- Extracted Videos -->
		<ExtractedVideos {handleProcessVideo} />

		<!-- Instructions -->
		<Instructions />
	</div>
</div>

<!-- Preferences Dialog -->
<PreferencesDialog bind:showPreferences />

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
