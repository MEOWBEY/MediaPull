<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { toast } from 'svelte-sonner';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import {
		Card,
		CardContent,
		CardDescription,
		CardHeader,
		CardTitle
	} from '$lib/components/ui/card';
	import { Badge } from '$lib/components/ui/badge';
	import * as Alert from '$lib/components/ui/alert';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu';
	import * as Dialog from '$lib/components/ui/dialog';
	import { Switch } from '$lib/components/ui/switch';
	import { Label } from '$lib/components/ui/label';
	import { Slider } from '$lib/components/ui/slider';

	import VideoPlayer from '$lib/components/VideoPlayer.svelte';

	// Lucide Icons
	import Download from 'lucide-svelte/icons/download';
	import Copy from 'lucide-svelte/icons/copy';
	import Loader2 from 'lucide-svelte/icons/loader-2';
	import Search from 'lucide-svelte/icons/search';
	import X from 'lucide-svelte/icons/x';
	import ChevronDown from 'lucide-svelte/icons/chevron-down';
	import Video from 'lucide-svelte/icons/video';
	import Monitor from 'lucide-svelte/icons/monitor';
	import FileText from 'lucide-svelte/icons/file-text';
	import Clock from 'lucide-svelte/icons/clock';
	import HardDrive from 'lucide-svelte/icons/hard-drive';
	import Trash2 from 'lucide-svelte/icons/trash-2';
	import Link2 from 'lucide-svelte/icons/link-2';
	import AlertCircle from 'lucide-svelte/icons/alert-circle';
	import Hammer from 'lucide-svelte/icons/hammer';
	import MonitorPlay from 'lucide-svelte/icons/monitor-play';
	import Settings from 'lucide-svelte/icons/settings';
	import Grid3X3 from 'lucide-svelte/icons/grid-3x3';
	import LayoutList from 'lucide-svelte/icons/layout-list';
	import Volume2 from 'lucide-svelte/icons/volume-2';
	import Palette from 'lucide-svelte/icons/palette';
	import Smartphone from 'lucide-svelte/icons/smartphone';
	import Play from 'lucide-svelte/icons/play';
	import Pause from 'lucide-svelte/icons/pause';
	import Keyboard from 'lucide-svelte/icons/keyboard';

	// Store Imports
	import {
		videoStore,
		uiState,
		apiCache,
		formatFileSize,
		debounce,
		organizeVideosBySourceAndType,
		type VideoFormat,
		type ExtractedVideoData,
		type ProcessedVideo
	} from '$lib/stores/app-state.svelte';

	// Reactive State
	let inputUrl = $state('');
	let operationTimer = $state(0);
	let timerInterval: NodeJS.Timeout | null = null;
	let abortController: AbortController | null = null;
	let processedVideoPreviewStates = $state(new Map<string, boolean>());
	let showPreferences = $state(false);
	let searchQuery = $state('');

	// Reactive Getters
	let isProcessing = $derived(videoStore.processing);
	let isExtracting = $derived(videoStore.extracting);
	let isOperationRunning = $derived(isProcessing || isExtracting);
	let extractedData = $derived(videoStore.extractedData);
	let processedVideos = $derived(videoStore.getSortedProcessedVideos());
	let processingError = $derived(videoStore.processingError);
	let extractionError = $derived(videoStore.extractionError);
	let hasErrors = $derived(Boolean(processingError || extractionError));
	let processingQueue = $derived(videoStore.processingQueue);
	let preferences = $derived(videoStore.preferences);

	// Computed Values
	let organizedVideos = $derived(organizeVideosBySourceAndType(extractedData?.formats || []));
	let hasExtractedData = $derived(extractedData !== null);
	let hasProcessedVideos = $derived(processedVideos.length > 0);
	let filteredProcessedVideos = $derived(
		searchQuery
			? processedVideos.filter(
					(v) =>
						v.filename?.toLowerCase().includes(searchQuery.toLowerCase()) ||
						v.title?.toLowerCase().includes(searchQuery.toLowerCase())
				)
			: processedVideos
	);

	let operationStatus = $derived(() => {
		if (isExtracting) return { color: 'bg-blue-500', text: 'Extracting...', pulse: false };
		if (isProcessing) return { color: 'bg-blue-500', text: 'Processing...', pulse: false };
		if (processingQueue.size > 0)
			return { color: 'bg-yellow-500', text: `${processingQueue.size} in queue`, pulse: false };
		if (hasProcessedVideos) return { color: 'bg-green-500', text: 'Ready', pulse: false };
		if (hasErrors) return { color: 'bg-red-500', text: 'Error', pulse: false };
		return { color: 'bg-gray-400', text: 'Idle', pulse: false };
	});

	// Apply theme and dynamic classes
	$effect(() => {
		if (typeof document !== 'undefined') {
			const root = document.documentElement;

			// Apply theme
			if (preferences.theme === 'dark') {
				root.classList.add('dark');
			} else if (preferences.theme === 'light') {
				root.classList.remove('dark');
			} else {
				// System theme
				const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
				if (isDark) root.classList.add('dark');
				else root.classList.remove('dark');
			}

			// Apply high contrast
			if (preferences.highContrast) {
				root.classList.add('high-contrast');
			} else {
				root.classList.remove('high-contrast');
			}

			// Apply compact mode
			if (preferences.compactMode) {
				root.classList.add('compact-mode');
			} else {
				root.classList.remove('compact-mode');
			}

			// Apply animations
			if (!preferences.animationsEnabled) {
				root.classList.add('no-animations');
			} else {
				root.classList.remove('no-animations');
			}
		}
	});

	// Lifecycle
	onMount(() => {
		inputUrl = videoStore.inputUrl;
		$effect(() => videoStore.updateInputUrl(inputUrl));
		if (isOperationRunning) startTimer();
		setupKeyboardShortcuts();
	});

	onDestroy(() => {
		stopTimer();
		if (abortController) abortController.abort();
	});

	$effect(() => {
		if (isOperationRunning && !timerInterval) startTimer();
		else if (!isOperationRunning && timerInterval) stopTimer();
	});

	// Timer Functions
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

	function formatTimer(seconds: number): string {
		const mins = Math.floor(seconds / 60);
		const secs = seconds % 60;
		return `${mins}:${secs.toString().padStart(2, '0')}`;
	}

	// Keyboard Shortcuts
	function setupKeyboardShortcuts() {
		const handleKeydown = (e: KeyboardEvent) => {
			if (!preferences.keyboardShortcuts) return;

			if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && !isOperationRunning) {
				e.preventDefault();
				handleExtractVideos();
			}
			if (e.key === 'Escape') {
				if (isOperationRunning) handleCancelOperation();
				else if (showPreferences) showPreferences = false;
			}
			if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
				e.preventDefault();
				document.getElementById('search-input')?.focus();
			}
		};
		document.addEventListener('keydown', handleKeydown);
		return () => document.removeEventListener('keydown', handleKeydown);
	}

	// API Operations
	async function handleExtractVideos() {
		if (!inputUrl.trim()) {
			toast.error('Please enter a valid URL');
			return;
		}
		if (!isValidUrl(inputUrl.trim())) {
			toast.error('Invalid URL format');
			return;
		}

		const cacheKey = `extract-${inputUrl.trim()}`;
		const cachedData = apiCache.get<ExtractedVideoData>(cacheKey);
		if (cachedData && preferences.cacheEnabled) {
			videoStore.setExtractedData(cachedData);
			toast.success('Loaded from cache');
			return;
		}

		abortController = new AbortController();
		videoStore.extracting = true;
		videoStore.extractionError = null;
		videoStore.reset();

		try {
			uiState.setLoading('extract', true);
			const response = await fetch('/api/extract-videos', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ url: inputUrl.trim() }),
				signal: abortController.signal
			});

			if (abortController.signal.aborted) return;
			const data = await response.json();

			if (data.success && data.video) {
				const extractedData: ExtractedVideoData = {
					...data.video,
					sourceUrl: inputUrl.trim(),
					totalFormats: data.video.formats?.length || 0
				};
				videoStore.setExtractedData(extractedData);
				if (preferences.cacheEnabled) {
					apiCache.set(cacheKey, extractedData, 30 * 60 * 1000);
				}
				toast.success(`Extracted ${extractedData.totalFormats} formats`);
			} else {
				throw new Error(data.error || 'Extraction failed');
			}
		} catch (error: any) {
			if (error.name === 'AbortError') toast.info('Extraction cancelled');
			else {
				videoStore.extractionError = error.message;
				toast.error(`Error: ${error.message}`);
			}
		} finally {
			videoStore.extracting = false;
			uiState.setLoading('extract', false);
			abortController = null;
		}
	}

	async function handleProcessVideo(video?: VideoFormat) {
		const targetUrl = video?.originalUrl || inputUrl.trim();
		if (!targetUrl) {
			toast.error('Please enter a valid URL');
			return;
		}

		const processKey = `${targetUrl}-${video?.quality || 'default'}`;
		const loadingKey = `process-${video?.id || 'direct'}`;

		if (video) videoStore.processingQueue.add(processKey);
		else {
			abortController = new AbortController();
			videoStore.processing = true;
			videoStore.reset();
		}

		try {
			uiState.setLoading(loadingKey, true);
			const response = await fetch('/api/process-video', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					userVideoUrl: targetUrl,
					quality: video?.quality,
					format: video?.extension
				}),
				signal: abortController?.signal
			});

			if (abortController?.signal.aborted) return;
			const data = await response.json();

			if (data.success && data.video) {
				const processedVideo: ProcessedVideo = {
					...data.video,
					processingTime: data.video.processingTime || 0,
					status: 'completed'
				};
				videoStore.addProcessedVideo(processedVideo);
				processedVideoPreviewStates.set(processedVideo.id, preferences.autoPreview);
				processedVideoPreviewStates = new Map(processedVideoPreviewStates);
				toast.success(`Processed in ${processedVideo.processingTime}ms`, {
					action: {
						label: 'Download',
						onClick: () => window.open(processedVideo.downloadUrl, '_blank')
					}
				});
			} else {
				throw new Error(data.error || 'Processing failed');
			}
		} catch (error: any) {
			if (error.name === 'AbortError') toast.info('Processing cancelled');
			else {
				videoStore.processingError = error.message;
				toast.error(`Error: ${error.message}`);
			}
		} finally {
			if (video) videoStore.processingQueue.delete(processKey);
			else {
				videoStore.processing = false;
				abortController = null;
			}
			uiState.setLoading(loadingKey, false);
		}
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

	// UI Helpers

	async function copyToClipboard(text: string, id: string) {
		try {
			await navigator.clipboard.writeText(text);
			toast.success('Copied to clipboard');
			const element = document.querySelector(`[data-copy-id="${id}"]`);
			if (element) {
				element.classList.add('text-green-500');
				setTimeout(() => element.classList.remove('text-green-500'), 2000);
			}
		} catch (error) {
			toast.error('Failed to copy');
		}
	}

	function isVideoProcessing(video: VideoFormat): boolean {
		const processKey = `${video.originalUrl}-${video.quality}`;
		return processingQueue.has(processKey);
	}

	function isProcessedVideoPreviewOpen(videoId: string): boolean {
		return processedVideoPreviewStates.get(videoId) ?? preferences.autoPreview;
	}

	function toggleProcessedVideoPreview(videoId: string) {
		const current = processedVideoPreviewStates.get(videoId) ?? preferences.autoPreview;
		processedVideoPreviewStates.set(videoId, !current);
		processedVideoPreviewStates = new Map(processedVideoPreviewStates);
	}

	function getBestQuality(typeGroup: any) {
		const resolutions = Object.entries(typeGroup.formats);
		const sortedResolutions = resolutions.sort((a, b) => {
			const aHeight = parseInt(a[0].replace('p', '')) || 0;
			const bHeight = parseInt(b[0].replace('p', '')) || 0;
			return bHeight - aHeight;
		});
		return sortedResolutions[0]?.[1] as VideoFormat;
	}

	function clearInput() {
		if (isOperationRunning) return;
		inputUrl = '';
		operationTimer = 0;
		videoStore.reset();
		toast.info('Input cleared');
	}

	function clearExtractedVideos() {
		videoStore.clearExtractedData();
		toast.info('Extracted data cleared');
	}

	function clearProcessedVideos() {
		videoStore.clearProcessedVideos();
		processedVideoPreviewStates.clear();
		toast.info('Processed videos cleared');
	}

	function handleKeyPress(event: KeyboardEvent) {
		if (!preferences.keyboardShortcuts) return;
		if (event.key === 'Enter' && !isOperationRunning) handleExtractVideos();
		if (event.key === 'Escape' && isOperationRunning) handleCancelOperation();
	}

	function isValidUrl(string: string): boolean {
		try {
			new URL(string);
			return true;
		} catch (_) {
			return false;
		}
	}

	const debouncedInputHandler = debounce((value: string) => {
		videoStore.updateInputUrl(value);
	}, 300);

	$effect(() => debouncedInputHandler(inputUrl));

	function getVideoQualities(
		video: VideoFormat,
		typeGroup: any
	): Array<{ src: string; label: string; resolution?: string }> {
		const qualities = [];
		Object.entries(typeGroup.formats).forEach(([resolution, format]: [string, any]) => {
			qualities.push({
				src: format.downloadUrl,
				label: resolution,
				resolution: format.resolution
			});
		});
		return qualities;
	}

	// Theme management
	function applyTheme() {
		if (typeof document === 'undefined') return;

		const root = document.documentElement;

		switch (preferences.theme) {
			case 'dark':
				root.classList.add('dark');
				break;
			case 'light':
				root.classList.remove('dark');
				break;
			case 'system':
			default:
				const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
				if (prefersDark) {
					root.classList.add('dark');
				} else {
					root.classList.remove('dark');
				}
				break;
		}
	}

	// Auto-clear cache function
	function autoCleanCache() {
		if (preferences.autoClearCache) {
			const stats = apiCache.getStats();
			if (stats.size > 50) {
				apiCache.clear();
				toast.info('Auto-cleared cache (50+ items)');
			}
		}
	}

	// Periodically clean cache if enabled
	onMount(() => {
		const interval = setInterval(autoCleanCache, 5 * 60 * 1000); // Every 5 minutes
		return () => clearInterval(interval);
	});
</script>

<svelte:head>
	<title>DirectLinker - Video Processing</title>
	<meta name="description" content="Extract and process videos from URLs efficiently" />
	<meta name="keywords" content="video processing, extraction, download" />
</svelte:head>

<div class="min-h-screen {preferences.compactMode ? 'compact-mode' : ''}">
	<div class="container mx-auto max-w-5xl px-4 py-6">
		<!-- Status Bar -->
		<div class="mb-6 flex items-center justify-between">
			<div class="flex items-center gap-3">
				<div
					class="flex items-center gap-2 rounded-lg bg-white px-3 py-2 shadow-sm dark:bg-gray-800"
				>
					<div class="h-2 w-2 rounded-full {operationStatus().color}"></div>
					<span class="text-sm font-medium">{operationStatus().text}</span>
				</div>
				{#if isOperationRunning}
					<div class="flex items-center gap-1 rounded-lg bg-blue-50 px-3 py-2 dark:bg-blue-900/30">
						<Clock class="h-3 w-3 text-blue-600 dark:text-blue-400" />
						<span class="font-mono text-sm text-blue-600 dark:text-blue-400"
							>{formatTimer(operationTimer)}</span
						>
					</div>
				{/if}
			</div>
			<div class="flex items-center gap-2">
				{#if preferences.saveBandwidth}
					<Badge variant="outline" class="text-xs">
						<Smartphone class="mr-1 h-3 w-3" />
						Bandwidth Saving
					</Badge>
				{/if}
				<Button variant="outline" size="sm" onclick={() => (showPreferences = true)}>
					<Settings class="h-4 w-4" />
				</Button>
			</div>
		</div>

		<!-- Main Input -->
		<Card class="mb-6 border shadow-sm {preferences.highContrast ? 'border-2' : ''}">
			<CardHeader class={preferences.compactMode ? 'pb-2' : 'pb-4'}>
				<CardTitle
					class="flex items-center gap-2 {preferences.compactMode ? 'text-base' : 'text-lg'}"
				>
					<Video class="h-5 w-5 text-blue-600" />
					Video Processing
				</CardTitle>
				<CardDescription>Enter a video URL to extract formats or process directly</CardDescription>
			</CardHeader>
			<CardContent class={preferences.compactMode ? 'space-y-2' : 'space-y-4'}>
				<div class="flex gap-2">
					<div class="relative flex-1">
						<Link2 class="absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-gray-500" />
						<Input
							id="video-url"
							bind:value={inputUrl}
							placeholder="https://example.com/video"
							disabled={isOperationRunning}
							class="cursor-text pl-10"
							onkeydown={handleKeyPress}
						/>
					</div>
					{#if inputUrl}
						<Button
							variant="outline"
							size="icon"
							onclick={clearInput}
							disabled={isOperationRunning}
							class="cursor-pointer"
						>
							<X class="h-4 w-4" />
						</Button>
					{/if}
				</div>
				<div class="flex flex-wrap gap-2">
					<Button
						onclick={handleExtractVideos}
						disabled={!inputUrl.trim() || isOperationRunning}
						class="cursor-pointer transition-all duration-200"
					>
						{#if isExtracting}
							<Loader2 class="mr-2 h-4 w-4 animate-spin" />
							Extracting...
						{:else}
							<Search class="mr-2 h-4 w-4" />
							Extract Formats
						{/if}
					</Button>
					<Button
						variant="secondary"
						onclick={() => handleProcessVideo()}
						disabled={!inputUrl.trim() || isOperationRunning}
						class="cursor-pointer border bg-gray-200 transition-all duration-200 hover:bg-gray-300 dark:bg-zinc-800 hover:dark:bg-zinc-700"
					>
						{#if isProcessing}
							<Loader2 class="mr-2 h-4 w-4 animate-spin" />
							Processing...
						{:else}
							<Hammer class="mr-2 h-4 w-4" />
							Process
						{/if}
					</Button>
					{#if isOperationRunning}
						<Button
							variant="destructive"
							onclick={handleCancelOperation}
							size="icon"
							class="animate-pulse cursor-pointer"
						>
							<X class="h-4 w-4" />
						</Button>
					{/if}
				</div>
			</CardContent>
		</Card>

		<!-- Errors -->
		{#if hasErrors}
			<Alert.Root variant="destructive" class="mb-6">
				<AlertCircle class="h-4 w-4" />
				<Alert.Description class="flex items-start justify-between">
					<div>
						<p class="mb-1 font-medium">Error</p>
						<p class="text-sm">{extractionError || processingError}</p>
					</div>
					<Button
						variant="outline"
						size="sm"
						onclick={() => videoStore.clearErrors()}
						class="cursor-pointer"
					>
						Dismiss
					</Button>
				</Alert.Description>
			</Alert.Root>
		{/if}

		<!-- Processed Videos -->
		{#if hasProcessedVideos}
			<Card class="mb-6 border shadow-sm {preferences.highContrast ? 'border-2' : ''}">
				<CardHeader class={preferences.compactMode ? 'py-3' : ''}>
					<div class="flex items-center justify-between">
						<CardTitle
							class="flex items-center gap-2 {preferences.compactMode ? 'text-base' : 'text-lg'}"
						>
							<Download class="h-5 w-5 text-green-600" />
							Processed Videos
							<Badge variant="secondary">{filteredProcessedVideos.length}</Badge>
						</CardTitle>
						<div class="flex gap-2">
							<DropdownMenu.Root>
								<DropdownMenu.Trigger>
									<Button variant="outline" size="sm" class="cursor-pointer">
										<LayoutList class="mr-2 h-4 w-4" />
										View
										<ChevronDown class="ml-1 h-3 w-3" />
									</Button>
								</DropdownMenu.Trigger>
								<DropdownMenu.Content>
									<DropdownMenu.Item
										onclick={() => videoStore.updatePreferences({ viewMode: 'grid' })}
										class="cursor-pointer"
									>
										<Grid3X3 class="mr-2 h-4 w-4" />
										Grid View
									</DropdownMenu.Item>
									<DropdownMenu.Item
										onclick={() => videoStore.updatePreferences({ viewMode: 'list' })}
										class="cursor-pointer"
									>
										<LayoutList class="mr-2 h-4 w-4" />
										List View
									</DropdownMenu.Item>
								</DropdownMenu.Content>
							</DropdownMenu.Root>
							<Button
								variant="outline"
								size="sm"
								onclick={clearProcessedVideos}
								class="cursor-pointer"
							>
								<Trash2 class="mr-2 h-4 w-4" />
								Clear
							</Button>
						</div>
					</div>
				</CardHeader>
				<CardContent>
					{#if processedVideos.length > 3}
						<div class="mb-4 flex gap-2">
							<div class="relative flex-1">
								<Search class="absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-gray-500" />
								<Input
									id="search-input"
									bind:value={searchQuery}
									placeholder="Search videos..."
									class="cursor-text pl-10"
								/>
							</div>
						</div>
					{/if}
					<div
						class="grid {preferences.compactMode ? 'gap-2' : 'gap-4'} {preferences.viewMode ===
						'grid'
							? 'sm:grid-cols-2'
							: 'grid-cols-1'}"
					>
						{#each filteredProcessedVideos as video (video.id)}
							<div
								class="group relative rounded-lg border {preferences.compactMode
									? 'p-2'
									: 'p-4'} {preferences.highContrast
									? 'border-2'
									: ''} shadow-sm transition-all duration-200 hover:shadow-md"
							>
								<div
									class="flex items-start justify-between gap-4 {preferences.compactMode
										? 'mb-2'
										: 'mb-3'}"
								>
									<div class="flex-1 {preferences.compactMode ? 'space-y-1' : 'space-y-2'}">
										<div class="flex items-center gap-2">
											<Badge variant="outline">{video.quality || 'Unknown'}</Badge>
											{#if video.fileSize}
												<span class="text-xs text-gray-500">{formatFileSize(video.fileSize)}</span>
											{/if}
										</div>
										{#if video.filename && preferences.showThumbnails}
											<p class="truncate text-sm text-gray-600 dark:text-gray-400">
												{video.filename}
											</p>
										{/if}
									</div>
									<div class="flex gap-1.5">
										<Button
											variant="ghost"
											size="icon"
											onclick={() => toggleProcessedVideoPreview(video.id)}
											class="cursor-pointer"
										>
											{#if isProcessedVideoPreviewOpen(video.id)}
												<Pause class="h-4 w-4" />
											{:else}
												<Play class="h-4 w-4" />
											{/if}
										</Button>
										<Button
											variant="outline"
											size="icon"
											onclick={() => copyToClipboard(video.downloadUrl, `processed-${video.id}`)}
											data-copy-id="processed-{video.id}"
											class="cursor-pointer"
										>
											<Copy class="h-4 w-4" />
										</Button>
										<Button
											onclick={() => window.open(video.downloadUrl, '_blank')}
											class="cursor-pointer bg-green-600 hover:bg-green-700"
											size="icon"
										>
											<Download class="h-4 w-4" />
										</Button>
									</div>
								</div>
								{#if isProcessedVideoPreviewOpen(video.id)}
									<div class="mt-2">
										<VideoPlayer
											src={video.downloadUrl}
											poster={preferences.showThumbnails ? video.thumbnail : ''}
											autoplay={preferences.autoPlay}
											muted={preferences.muteByDefault}
											preload={preferences.preloadMetadata ? 'metadata' : 'none'}
											showControls={preferences.showControls}
											volume={preferences.videoVolume}
											playbackRate={preferences.playbackRate}
											loopVideo={preferences.loopVideos}
											enablePiP={preferences.pictureInPicture}
											qualities={[{ src: video.downloadUrl, label: video.quality || 'Default' }]}
										/>
									</div>
								{/if}
							</div>
						{/each}
					</div>
				</CardContent>
			</Card>
		{/if}

		<!-- Extracted Videos -->
		{#if hasExtractedData}
			<Card class="mb-6 border shadow-sm {preferences.highContrast ? 'border-2' : ''}">
				<CardHeader class={preferences.compactMode ? 'py-3' : ''}>
					<div class="flex items-center justify-between">
						<CardTitle
							class="flex items-center gap-2 {preferences.compactMode ? 'text-base' : 'text-lg'}"
						>
							<MonitorPlay class="h-5 w-5 text-blue-600" />
							Available Formats
							{#if preferences.groupBySource}
								<Badge variant="outline">Grouped</Badge>
							{/if}
						</CardTitle>
						<Button
							variant="outline"
							size="sm"
							onclick={clearExtractedVideos}
							class="cursor-pointer"
						>
							<Trash2 class="mr-2 h-4 w-4" />
							Clear
						</Button>
					</div>
					<CardDescription>
						{extractedData?.title || 'Video'} • {extractedData?.totalFormats} formats
						{#if extractedData?.duration}
							• {Math.floor(extractedData.duration / 60)}:{(extractedData.duration % 60)
								.toString()
								.padStart(2, '0')}
						{/if}
					</CardDescription>
				</CardHeader>
				<CardContent>
					{#each Object.entries(organizedVideos) as [groupKey, sourceGroup]}
						<div class="{preferences.compactMode ? 'mb-3' : 'mb-6'} last:mb-0">
							{#each Object.entries(sourceGroup.types) as [type, typeGroup]}
								<div
									class="rounded-lg border {preferences.compactMode
										? 'p-2'
										: 'p-4'} {preferences.highContrast ? 'border-2' : ''}"
								>
									<div
										class="flex items-center justify-between {preferences.compactMode
											? 'mb-2'
											: 'mb-3'}"
									>
										<div class="flex items-center gap-2">
											<div>
												<h4
													class="font-semibold text-gray-900 capitalize dark:text-gray-100 {preferences.compactMode
														? 'text-sm'
														: ''}"
												>
													{type} Formats
												</h4>
												<p
													class="text-gray-600 dark:text-gray-400 {preferences.compactMode
														? 'text-xs'
														: 'text-sm'}"
												>
													{Object.keys(typeGroup.formats).length} options
												</p>
											</div>
										</div>
										<DropdownMenu.Root>
											<DropdownMenu.Trigger>
												<Button variant="outline" size="sm" class="cursor-pointer">
													<MonitorPlay class="mr-2 h-4 w-4" />
													Options
													<ChevronDown class="ml-2 h-4 w-4" />
												</Button>
											</DropdownMenu.Trigger>
											<DropdownMenu.Content align="end" class="w-80">
												<DropdownMenu.Label>Quality Options</DropdownMenu.Label>
												<DropdownMenu.Separator />
												{#each Object.entries(typeGroup.formats) as [resolution, video]}
													<div
														class="mx-1 flex items-center justify-between rounded p-2 hover:bg-gray-50 dark:hover:bg-gray-700"
													>
														<div class="flex items-center gap-2">
															<Badge variant="outline">{resolution}</Badge>
															{#if video.fileSize}
																<span class="text-sm text-gray-600 dark:text-gray-400">
																	{formatFileSize(video.fileSize)}
																</span>
															{/if}
															{#if video.fps}
																<span class="text-xs text-gray-500">{video.fps}fps</span>
															{/if}
														</div>
														<div class="flex gap-1">
															{#if !video.isHLS && type !== 'hls' && type !== 'dash'}
																<Button
																	variant="ghost"
																	size="icon"
																	onclick={() => handleProcessVideo(video)}
																	disabled={isVideoProcessing(video) || isOperationRunning}
																	class="h-7 w-7 cursor-pointer"
																>
																	{#if isVideoProcessing(video)}
																		<Loader2 class="h-3 w-3 animate-spin" />
																	{:else}
																		<Hammer class="h-3 w-3" />
																	{/if}
																</Button>
															{/if}
															<Button
																variant="ghost"
																size="icon"
																onclick={() =>
																	copyToClipboard(
																		video.downloadUrl,
																		`${groupKey}-${type}-${resolution}`
																	)}
																class="h-7 w-7 cursor-pointer"
																data-copy-id="{groupKey}-{type}-{resolution}"
															>
																<Copy class="h-3 w-3" />
															</Button>
															{#if !video.isHLS && type !== 'hls' && type !== 'dash'}
																<Button
																	variant="ghost"
																	size="icon"
																	onclick={() => {
																		const link = document.createElement('a');
																		link.href = video.downloadUrl;
																		link.download = video.filename || 'video';
																		link.click();
																	}}
																	class="h-7 w-7 cursor-pointer"
																>
																	<Download class="h-3 w-3" />
																</Button>
															{/if}
														</div>
													</div>
												{/each}
											</DropdownMenu.Content>
										</DropdownMenu.Root>
									</div>
									{#if getBestQuality(typeGroup)}
										<div class="overflow-hidden rounded-lg bg-black">
											<VideoPlayer
												src={getBestQuality(typeGroup)?.downloadUrl}
												poster={preferences.showThumbnails
													? getBestQuality(typeGroup)?.thumbnail
													: ''}
												autoplay={preferences.autoPlay}
												muted={preferences.muteByDefault}
												preload={preferences.preloadMetadata ? 'metadata' : 'none'}
												showControls={preferences.showControls}
												volume={preferences.videoVolume}
												playbackRate={preferences.playbackRate}
												loopVideo={preferences.loopVideos}
												enablePiP={preferences.pictureInPicture}
												qualities={getVideoQualities(getBestQuality(typeGroup), typeGroup)}
											/>
										</div>
									{/if}
								</div>
							{/each}
						</div>
					{/each}
				</CardContent>
			</Card>
		{/if}

		<!-- Instructions -->
		<Card class="border shadow-sm {preferences.highContrast ? 'border-2' : ''}">
			<CardHeader class={preferences.compactMode ? 'py-3' : ''}>
				<CardTitle
					class="flex items-center gap-2 {preferences.compactMode ? 'text-base' : 'text-lg'}"
				>
					<FileText class="h-5 w-5 text-gray-600" />
					How to Use
				</CardTitle>
			</CardHeader>
			<CardContent>
				<div class="grid {preferences.compactMode ? 'gap-2' : 'gap-4'} sm:grid-cols-2">
					<div class={preferences.compactMode ? 'space-y-2' : 'space-y-3'}>
						<div class="flex items-start gap-2">
							<Badge
								variant="outline"
								class="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center text-xs">1</Badge
							>
							<div>
								<h4 class="mb-1 font-medium {preferences.compactMode ? 'text-sm' : ''}">
									Extract Formats
								</h4>
								<p
									class="text-gray-600 dark:text-gray-400 {preferences.compactMode
										? 'text-xs'
										: 'text-sm'}"
								>
									Enter a video URL and click "Extract Formats" to see available options.
								</p>
							</div>
						</div>
						<div class="flex items-start gap-2">
							<Badge
								variant="outline"
								class="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center text-xs">2</Badge
							>
							<div>
								<h4 class="mb-1 font-medium {preferences.compactMode ? 'text-sm' : ''}">
									Choose Quality
								</h4>
								<p
									class="text-gray-600 dark:text-gray-400 {preferences.compactMode
										? 'text-xs'
										: 'text-sm'}"
								>
									Select your preferred format and quality from the list.
								</p>
							</div>
						</div>
						<div class="flex items-start gap-2">
							<Badge
								variant="outline"
								class="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center text-xs">3</Badge
							>
							<div>
								<h4 class="mb-1 font-medium {preferences.compactMode ? 'text-sm' : ''}">
									Process & Download
								</h4>
								<p
									class="text-gray-600 dark:text-gray-400 {preferences.compactMode
										? 'text-xs'
										: 'text-sm'}"
								>
									Process formats or use "Process" for quick downloads.
								</p>
							</div>
						</div>
					</div>
					<div class={preferences.compactMode ? 'space-y-2' : 'space-y-3'}>
						<div class="flex items-start gap-2">
							<Badge
								variant="outline"
								class="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center text-xs">4</Badge
							>
							<div>
								<h4 class="mb-1 font-medium {preferences.compactMode ? 'text-sm' : ''}">Caching</h4>
								<p
									class="text-gray-600 dark:text-gray-400 {preferences.compactMode
										? 'text-xs'
										: 'text-sm'}"
								>
									Extracted formats are cached for quick access.
								</p>
							</div>
						</div>
						<div class="flex items-start gap-2">
							<Badge
								variant="outline"
								class="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center text-xs">5</Badge
							>
							<div>
								<h4 class="mb-1 font-medium {preferences.compactMode ? 'text-sm' : ''}">
									Shortcuts
								</h4>
								<p
									class="text-gray-600 dark:text-gray-400 {preferences.compactMode
										? 'text-xs'
										: 'text-sm'}"
								>
									{#if preferences.keyboardShortcuts}
										Use Ctrl+Enter to extract, Escape to cancel, Ctrl+K to search.
									{:else}
										Keyboard shortcuts are disabled in preferences.
									{/if}
								</p>
							</div>
						</div>
						<div class="flex items-start gap-2">
							<Badge
								variant="outline"
								class="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center text-xs">6</Badge
							>
							<div>
								<h4 class="mb-1 font-medium {preferences.compactMode ? 'text-sm' : ''}">
									Video Player
								</h4>
								<p
									class="text-gray-600 dark:text-gray-400 {preferences.compactMode
										? 'text-xs'
										: 'text-sm'}"
								>
									Built-in player supports HLS and standard formats with quality switching.
								</p>
							</div>
						</div>
					</div>
				</div>
			</CardContent>
		</Card>
	</div>
</div>

<!-- Preferences Dialog -->
<Dialog.Root bind:open={showPreferences}>
	<Dialog.Content class="m-4 mx-auto h-full max-w-4xl overflow-auto p-4 sm:p-6">
		<div class="space-y-6 pb-4 sm:space-y-8 sm:pb-6">
			<!-- Interface Section -->
			<section class="space-y-4">
				<h4 class="flex items-center gap-2 border-b pb-2 text-base font-semibold">
					<Monitor class="h-4 w-4 text-blue-600" />
					Interface
				</h4>
				<div class="grid grid-cols-1 gap-3 sm:grid-cols-2 sm:gap-4 lg:grid-cols-2">
					{#each [{ id: 'auto-preview', label: 'Auto-preview videos', key: 'autoPreview' }, { id: 'show-thumbnails', label: 'Show thumbnails', key: 'showThumbnails' }, { id: 'group-by-source', label: 'Group by source', key: 'groupBySource' }, { id: 'animations-enabled', label: 'Enable animations', key: 'animationsEnabled' }] as setting}
						<div
							class="flex items-center justify-between rounded-lg bg-gray-50 p-3 transition-colors hover:bg-gray-100 dark:bg-gray-800/50 dark:hover:bg-gray-800"
						>
							<Label for={setting.id} class="cursor-pointer text-sm font-medium">
								{setting.label}
							</Label>
							<Switch
								id={setting.id}
								checked={preferences[setting.key] || false}
								onCheckedChange={(checked) =>
									videoStore.updatePreferences({ [setting.key]: checked })}
							/>
						</div>
					{/each}
				</div>
			</section>

			<!-- Playback Section -->
			<section class="space-y-4">
				<h4 class="flex items-center gap-2 border-b pb-2 text-base font-semibold">
					<Volume2 class="h-4 w-4 text-green-600" />
					Playback
				</h4>
				<div class="grid grid-cols-1 gap-3 sm:grid-cols-2 sm:gap-4 lg:grid-cols-2">
					{#each [{ id: 'auto-play', label: 'Auto-play videos', key: 'autoPlay' }, { id: 'mute-by-default', label: 'Mute by default', key: 'muteByDefault' }, { id: 'loop-videos', label: 'Loop videos', key: 'loopVideos' }, { id: 'preload-metadata', label: 'Preload metadata', key: 'preloadMetadata', defaultTrue: true }] as setting}
						<div
							class="flex items-center justify-between rounded-lg bg-gray-50 p-3 transition-colors hover:bg-gray-100 dark:bg-gray-800/50 dark:hover:bg-gray-800"
						>
							<Label for={setting.id} class="cursor-pointer text-sm font-medium">
								{setting.label}
							</Label>
							<Switch
								id={setting.id}
								checked={setting.defaultTrue
									? preferences[setting.key] !== false
									: preferences[setting.key] || false}
								onCheckedChange={(checked) =>
									videoStore.updatePreferences({ [setting.key]: checked })}
							/>
						</div>
					{/each}
				</div>

				<!-- Volume Control -->
				<div class="space-y-2">
					<Label class="text-sm font-medium">Default Volume</Label>
					<div class="flex items-center gap-4">
						<Slider
							value={[preferences.videoVolume * 100]}
							onValueChange={(value: any) =>
								videoStore.updatePreferences({ videoVolume: value[0] / 100 })}
							max={100}
							step={5}
							class="flex-1"
						/>
						<span class="min-w-12 text-sm text-gray-600">
							{Math.round(preferences.videoVolume * 100)}%
						</span>
					</div>
				</div>

				<!-- Playback Speed -->
				<div class="space-y-2">
					<Label class="text-sm font-medium">Default Playback Speed</Label>
					<div class="flex items-center gap-4">
						<Slider
							value={[preferences.playbackRate]}
							onValueChange={(value) => videoStore.updatePreferences({ playbackRate: value[0] })}
							min={0.25}
							max={2}
							step={0.25}
							class="flex-1"
						/>
						<span class="min-w-12 text-sm text-gray-600">
							{preferences.playbackRate}x
						</span>
					</div>
				</div>
			</section>

			<!-- Advanced Playback Section -->
			<section class="space-y-4">
				<h4 class="flex items-center gap-2 border-b pb-2 text-base font-semibold">
					<Play class="h-4 w-4 text-purple-600" />
					Advanced Playback
				</h4>
				<div class="grid grid-cols-1 gap-3 sm:grid-cols-2 sm:gap-4">
					{#each [{ id: 'show-controls', label: 'Show player controls', key: 'showControls', defaultTrue: true }, { id: 'picture-in-picture', label: 'Enable Picture-in-Picture', key: 'pictureInPicture', defaultTrue: true }, { id: 'skip-intro', label: 'Skip intro segments', key: 'skipIntro' }, { id: 'auto-next', label: 'Auto-play next video', key: 'autoNext' }] as setting}
						<div
							class="flex items-center justify-between rounded-lg bg-gray-50 p-3 transition-colors hover:bg-gray-100 dark:bg-gray-800/50 dark:hover:bg-gray-800"
						>
							<Label for={setting.id} class="cursor-pointer text-sm font-medium">
								{setting.label}
							</Label>
							<Switch
								id={setting.id}
								checked={setting.defaultTrue
									? preferences[setting.key] !== false
									: preferences[setting.key] || false}
								onCheckedChange={(checked) =>
									videoStore.updatePreferences({ [setting.key]: checked })}
							/>
						</div>
					{/each}
				</div>
			</section>

			<!-- View Mode Section -->
			<section class="space-y-4">
				<h4 class="flex items-center gap-2 border-b pb-2 text-base font-semibold">
					<LayoutList class="h-4 w-4 text-purple-600" />
					View Mode
				</h4>
				<div class="flex flex-col gap-2 sm:flex-row">
					<Button
						variant={preferences.viewMode === 'grid' ? 'default' : 'outline'}
						size="sm"
						onclick={() => videoStore.updatePreferences({ viewMode: 'grid' })}
						class="flex-1 cursor-pointer justify-center sm:flex-none sm:justify-start"
					>
						<Grid3X3 class="mr-2 h-4 w-4" />
						Grid View
					</Button>
					<Button
						variant={preferences.viewMode === 'list' ? 'default' : 'outline'}
						size="sm"
						onclick={() => videoStore.updatePreferences({ viewMode: 'list' })}
						class="flex-1 cursor-pointer justify-center sm:flex-none sm:justify-start"
					>
						<LayoutList class="mr-2 h-4 w-4" />
						List View
					</Button>
				</div>
			</section>

			<!-- Theme Section -->
			<section class="space-y-4">
				<h4 class="flex items-center gap-2 border-b pb-2 text-base font-semibold">
					<Palette class="h-4 w-4 text-pink-600" />
					Theme & Appearance
				</h4>

				<!-- Theme Selection -->
				<div class="space-y-2">
					<Label class="text-sm font-medium">Theme</Label>
					<div class="flex flex-col gap-2 sm:flex-row">
						<Button
							variant={preferences.theme === 'light' ? 'default' : 'outline'}
							size="sm"
							onclick={() => videoStore.updatePreferences({ theme: 'light' })}
							class="flex-1 cursor-pointer justify-center sm:flex-none sm:justify-start"
						>
							Light
						</Button>
						<Button
							variant={preferences.theme === 'dark' ? 'default' : 'outline'}
							size="sm"
							onclick={() => videoStore.updatePreferences({ theme: 'dark' })}
							class="flex-1 cursor-pointer justify-center sm:flex-none sm:justify-start"
						>
							Dark
						</Button>
						<Button
							variant={preferences.theme === 'system' ? 'default' : 'outline'}
							size="sm"
							onclick={() => videoStore.updatePreferences({ theme: 'system' })}
							class="flex-1 cursor-pointer justify-center sm:flex-none sm:justify-start"
						>
							System
						</Button>
					</div>
				</div>

				<div class="grid grid-cols-1 gap-3 sm:grid-cols-2 sm:gap-4">
					{#each [{ id: 'compact-mode', label: 'Compact mode', key: 'compactMode' }, { id: 'high-contrast', label: 'High contrast', key: 'highContrast' }] as setting}
						<div
							class="flex items-center justify-between rounded-lg bg-gray-50 p-3 transition-colors hover:bg-gray-100 dark:bg-gray-800/50 dark:hover:bg-gray-800"
						>
							<Label for={setting.id} class="cursor-pointer text-sm font-medium">
								{setting.label}
							</Label>
							<Switch
								id={setting.id}
								checked={preferences[setting.key] || false}
								onCheckedChange={(checked) =>
									videoStore.updatePreferences({ [setting.key]: checked })}
							/>
						</div>
					{/each}
				</div>
			</section>

			<!-- Mobile Section -->
			<section class="space-y-4">
				<h4 class="flex items-center gap-2 border-b pb-2 text-base font-semibold">
					<Smartphone class="h-4 w-4 text-orange-600" />
					Mobile Experience
				</h4>
				<div class="grid grid-cols-1 gap-3 sm:grid-cols-2 sm:gap-4">
					{#each [{ id: 'mobile-optimized', label: 'Mobile optimized', key: 'mobileOptimized', defaultTrue: true }, { id: 'touch-friendly', label: 'Touch friendly', key: 'touchFriendly', defaultTrue: true }, { id: 'save-bandwidth', label: 'Save bandwidth', key: 'saveBandwidth' }, { id: 'offline-mode', label: 'Offline mode', key: 'offlineMode' }] as setting}
						<div
							class="flex items-center justify-between rounded-lg bg-gray-50 p-3 transition-colors hover:bg-gray-100 dark:bg-gray-800/50 dark:hover:bg-gray-800"
						>
							<Label for={setting.id} class="cursor-pointer text-sm font-medium">
								{setting.label}
							</Label>
							<Switch
								id={setting.id}
								checked={setting.defaultTrue
									? preferences[setting.key] !== false
									: preferences[setting.key] || false}
								onCheckedChange={(checked) =>
									videoStore.updatePreferences({ [setting.key]: checked })}
							/>
						</div>
					{/each}
				</div>
			</section>

			<!-- Controls Section -->
			<section class="space-y-4">
				<h4 class="flex items-center gap-2 border-b pb-2 text-base font-semibold">
					<Keyboard class="h-4 w-4 text-indigo-600" />
					Controls & Shortcuts
				</h4>
				<div class="grid grid-cols-1 gap-3 sm:grid-cols-1 sm:gap-4">
					<div
						class="flex items-center justify-between rounded-lg bg-gray-50 p-3 transition-colors hover:bg-gray-100 dark:bg-gray-800/50 dark:hover:bg-gray-800"
					>
						<Label for="keyboard-shortcuts" class="cursor-pointer text-sm font-medium">
							Enable keyboard shortcuts
						</Label>
						<Switch
							id="keyboard-shortcuts"
							checked={preferences.keyboardShortcuts !== false}
							onCheckedChange={(checked) =>
								videoStore.updatePreferences({ keyboardShortcuts: checked })}
						/>
					</div>
				</div>
				{#if preferences.keyboardShortcuts}
					<div class="rounded-lg border p-4 text-sm">
						<h5 class="mb-2 font-medium">Available Shortcuts:</h5>
						<div class="grid grid-cols-1 gap-1 sm:grid-cols-2">
							<div>
								<kbd class="rounded bg-gray-200 px-1 dark:bg-gray-700">Ctrl+Enter</kbd> - Extract videos
							</div>
							<div>
								<kbd class="rounded bg-gray-200 px-1 dark:bg-gray-700">Escape</kbd> - Cancel operation
							</div>
							<div>
								<kbd class="rounded bg-gray-200 px-1 dark:bg-gray-700">Ctrl+K</kbd> - Focus search
							</div>
							<div>
								<kbd class="rounded bg-gray-200 px-1 dark:bg-gray-700">Space</kbd> - Play/pause video
							</div>
						</div>
					</div>
				{/if}
			</section>

			<!-- Cache & Storage Section -->
			<section class="space-y-4">
				<h4 class="flex items-center gap-2 border-b pb-2 text-base font-semibold">
					<HardDrive class="h-4 w-4 text-red-600" />
					Cache & Storage
				</h4>

				<!-- Stats Cards -->
				<div class="grid grid-cols-1 gap-3 sm:grid-cols-3 sm:gap-4">
					<div
						class="rounded-lg border border-blue-200 bg-gradient-to-br from-blue-50 to-blue-100 p-4 text-center dark:border-blue-800 dark:from-blue-900/20 dark:to-blue-800/20"
					>
						<div class="text-2xl font-bold text-blue-700 sm:text-3xl dark:text-blue-300">
							{apiCache.getStats().size}
						</div>
						<div class="text-xs font-medium text-blue-600 sm:text-sm dark:text-blue-400">
							Cached Items
						</div>
					</div>
					<div
						class="rounded-lg border border-green-200 bg-gradient-to-br from-green-50 to-green-100 p-4 text-center dark:border-green-800 dark:from-green-900/20 dark:to-green-800/20"
					>
						<div class="text-2xl font-bold text-green-700 sm:text-3xl dark:text-green-300">
							{Math.round(apiCache.getStats().hitRate)}%
						</div>
						<div class="text-xs font-medium text-green-600 sm:text-sm dark:text-green-400">
							Hit Rate
						</div>
					</div>
					<div
						class="rounded-lg border border-purple-200 bg-gradient-to-br from-purple-50 to-purple-100 p-4 text-center dark:border-purple-800 dark:from-purple-900/20 dark:to-purple-800/20"
					>
						<div class="text-2xl font-bold text-purple-700 sm:text-3xl dark:text-purple-300">
							{processedVideos.length}
						</div>
						<div class="text-xs font-medium text-purple-600 sm:text-sm dark:text-purple-400">
							Processed
						</div>
					</div>
				</div>

				<!-- Cache Controls -->
				<div class="grid grid-cols-1 gap-3 sm:grid-cols-2 sm:gap-4">
					{#each [{ id: 'cache-enabled', label: 'Enable caching', key: 'cacheEnabled', defaultTrue: true }, { id: 'auto-clear-cache', label: 'Auto clear cache', key: 'autoClearCache' }] as setting}
						<div
							class="flex items-center justify-between rounded-lg bg-gray-50 p-3 transition-colors hover:bg-gray-100 dark:bg-gray-800/50 dark:hover:bg-gray-800"
						>
							<Label for={setting.id} class="cursor-pointer text-sm font-medium">
								{setting.label}
							</Label>
							<Switch
								id={setting.id}
								checked={setting.defaultTrue
									? preferences[setting.key] !== false
									: preferences[setting.key] || false}
								onCheckedChange={(checked) =>
									videoStore.updatePreferences({ [setting.key]: checked })}
							/>
						</div>
					{/each}
				</div>

				<Button
					variant="outline"
					size="sm"
					onclick={() => {
						apiCache.clear();
						toast.success('Cache cleared successfully');
					}}
					class="w-full cursor-pointer transition-colors hover:border-red-300 hover:bg-red-50 hover:text-red-700 dark:hover:border-red-700 dark:hover:bg-red-900/10 dark:hover:text-red-400"
				>
					<Trash2 class="mr-2 h-4 w-4" />
					Clear All Cache
				</Button>
			</section>

			<!-- Reset Section -->
			<section class="space-y-4">
				<h4 class="flex items-center gap-2 border-b pb-2 text-base font-semibold">
					<AlertCircle class="h-4 w-4 text-red-600" />
					Reset & Defaults
				</h4>
				<div class="flex flex-col gap-3 sm:flex-row sm:gap-4">
					<Button
						variant="outline"
						onclick={() => {
							videoStore.updatePreferences({
								theme: 'system',
								viewMode: 'grid',
								sortBy: 'date',
								sortOrder: 'desc',
								autoPreview: true,
								showThumbnails: true,
								groupBySource: true,
								animationsEnabled: true,
								compactMode: false,
								autoPlay: false,
								muteByDefault: true,
								loopVideos: false,
								preloadMetadata: true,
								showControls: true,
								mobileOptimized: true,
								touchFriendly: true,
								saveBandwidth: false,
								offlineMode: false,
								cacheEnabled: true,
								autoClearCache: false,
								highContrast: false,
								videoVolume: 0.8,
								playbackRate: 1.0,
								skipIntro: false,
								autoNext: false,
								pictureInPicture: true,
								keyboardShortcuts: true
							});
							toast.success('Preferences reset to defaults');
						}}
						class="flex-1 cursor-pointer"
					>
						Reset to Defaults
					</Button>
					<Button
						variant="destructive"
						onclick={() => {
							videoStore.reset();
							apiCache.clear();
							localStorage.clear();
							toast.success('All data cleared');
						}}
						class="flex-1 cursor-pointer"
					>
						<Trash2 class="mr-2 h-4 w-4" />
						Clear All Data
					</Button>
				</div>
			</section>
		</div>
	</Dialog.Content>
</Dialog.Root>

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

	:global(.compact-mode .card) {
		padding: 0.5rem;
	}

	:global(.compact-mode .space-y-4 > * + *) {
		margin-top: 0.5rem;
	}

	:global(.compact-mode .space-y-3 > * + *) {
		margin-top: 0.375rem;
	}

	:global(.compact-mode .space-y-2 > * + *) {
		margin-top: 0.25rem;
	}
</style>
