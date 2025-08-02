<script lang="ts">
	import { onDestroy } from 'svelte';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import Play from 'lucide-svelte/icons/play';
	import Loader2 from 'lucide-svelte/icons/loader-2';
	import FileVideo from 'lucide-svelte/icons/file-video';
	import Copy from 'lucide-svelte/icons/copy';
	import Link2 from 'lucide-svelte/icons/link-2';
	import Download from 'lucide-svelte/icons/download';
	import Trash2 from 'lucide-svelte/icons/trash-2';
	import AlertCircle from 'lucide-svelte/icons/alert-circle';
	import X from 'lucide-svelte/icons/x';
	import Clock from 'lucide-svelte/icons/clock';
	import Check from 'lucide-svelte/icons/check';
	import List from 'lucide-svelte/icons/list';
	import Eye from 'lucide-svelte/icons/eye';
	import VideoPlayer from '$lib/components/VideoPlayer.svelte';

	import {
		videoUrl,
		processing,
		extracting,
		result,
		addLog,
		processedVideos,
		addProcessedVideo,
		extractedVideoData,
		setExtractedVideoData,
		clearExtractedVideoData,
		clearProcessedVideos,
		previewStates,
		togglePreview,
		copySuccess,
		setCopySuccess,
		extractionError,
		processingVideos,
		addProcessingVideo,
		removeProcessingVideo,
		resetAllState
	} from '$lib/stores/videoStore';

	// Component State
	let inputElement = $state<HTMLInputElement>();
	let abortController = $state<AbortController | null>(null);
	let timer = $state(0);
	let timerInterval: NodeJS.Timeout | null = null;

	// Local state for processed video previews (default open)
	let processedVideoPreviewStates = $state(new Map<string, boolean>());

	// Derived State
	const isOperationRunning = $derived($processing || $extracting);
	const hasError = $derived($result?.error);
	const anyError = $derived(hasError || $extractionError);
	const extractedVideos = $derived($extractedVideoData?.formats || []);

	const operationStatusColor = $derived(() => {
		if (isOperationRunning) return 'animate-pulse bg-blue-500';
		if ($processedVideos.length > 0) return 'bg-green-500';
		if (anyError) return 'bg-red-500';
		return 'bg-zinc-400';
	});

	onDestroy(() => {
		stopTimer();
	});

	// Timer Functions
	function startTimer() {
		timer = 0;
		timerInterval = setInterval(() => timer++, 1000);
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

	function formatFileSize(bytes?: number): string {
		if (!bytes) return 'Unknown';
		const sizes = ['B', 'KB', 'MB', 'GB'];
		const i = Math.floor(Math.log(bytes) / Math.log(1024));
		return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${sizes[i]}`;
	}

	function formatDuration(seconds: number): string {
		const hours = Math.floor(seconds / 3600);
		const mins = Math.floor((seconds % 3600) / 60);
		const secs = seconds % 60;

		if (hours > 0) {
			return `${hours}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
		}
		return `${mins}:${secs.toString().padStart(2, '0')}`;
	}

	function safeGet(obj: any, path: string, fallback: string = 'Unknown'): string {
		return obj?.[path] || fallback;
	}

	// Toggle processed video preview
	function toggleProcessedVideoPreview(videoId: string) {
		const currentState = processedVideoPreviewStates.get(videoId) ?? true; // Default open
		processedVideoPreviewStates.set(videoId, !currentState);
		processedVideoPreviewStates = new Map(processedVideoPreviewStates);
	}

	// Check if processed video preview is open (default true)
	function isProcessedVideoPreviewOpen(videoId: string): boolean {
		return processedVideoPreviewStates.get(videoId) ?? true;
	}

	// Core Logic
	async function processVideo(url?: string, quality?: string, format?: string) {
		const targetUrl = url || $videoUrl.trim();
		if (!targetUrl || isOperationRunning) return;

		const processKey = `${targetUrl}-${quality || 'default'}`;
		if (url) {
			addProcessingVideo(processKey);
		}

		abortController = new AbortController();
		processing.set(true);
		if (!url) resetAllState();
		startTimer();

		try {
			const response = await fetch('/api/process-video', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					userVideoUrl: targetUrl,
					quality,
					format
				}),
				signal: abortController.signal
			});

			if (abortController.signal.aborted) return;

			const data = await response.json();
			if (data.success && data.video) {
				// Create processed video object with consistent structure
				const processedVideo = {
					...data.video,
					filesize: data.video.fileSize ? formatFileSize(data.video.fileSize) : 'Unknown'
				};

				addProcessedVideo(processedVideo);
				// Set default preview state to open for new processed videos
				processedVideoPreviewStates.set(processedVideo.id, true);
				processedVideoPreviewStates = new Map(processedVideoPreviewStates);

				addLog(`Video processed successfully in ${data.video.processingTime || 0}ms!`, 'success');
			} else {
				throw new Error(data.error || 'Processing failed');
			}
		} catch (error: any) {
			if (error.name === 'AbortError') {
				addLog('Operation cancelled', 'info');
			} else {
				result.set({ success: false, error: error.message });
				addLog(`Error: ${error.message}`, 'error');
			}
		} finally {
			processing.set(false);
			abortController = null;
			stopTimer();
			if (url) {
				removeProcessingVideo(processKey);
			}
		}
	}

	async function extractVideos() {
		const url = $videoUrl.trim();
		if (!url || isOperationRunning) return;

		abortController = new AbortController();
		extracting.set(true);
		resetAllState();
		startTimer();

		try {
			const response = await fetch('/api/extract-videos', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ url }),
				signal: abortController.signal
			});

			if (abortController.signal.aborted) return;

			const data = await response.json();
			if (data.success && data.video) {
				setExtractedVideoData({
					...data.video,
					sourceUrl: url
				});
				addLog(`Found ${data.video.totalFormats} video formats!`, 'success');
			} else {
				throw new Error(data.error || 'Extraction failed');
			}
		} catch (error: any) {
			if (error.name === 'AbortError') {
				addLog('Operation cancelled', 'info');
			} else {
				extractionError.set(error.message);
				addLog(`Error: ${error.message}`, 'error');
			}
		} finally {
			extracting.set(false);
			abortController = null;
			stopTimer();
		}
	}

	function cancelOperation() {
		if (abortController) {
			abortController.abort();
			addLog('Cancelling operation...', 'info');
		}
	}

	// UI Handlers
	async function copyToClipboard(text: string, id = '') {
		try {
			await navigator.clipboard.writeText(text);
			setCopySuccess(id);
			addLog('Link copied!', 'info');
		} catch (error) {
			addLog('Copy failed', 'error');
		}
	}

	function handleKeyPress(event: KeyboardEvent) {
		if (event.key === 'Enter' && !isOperationRunning) processVideo();
		if (event.key === 'Escape' && isOperationRunning) cancelOperation();
	}

	function clearInput() {
		if (isOperationRunning) return;
		videoUrl.set('');
		timer = 0;
		resetAllState();
		inputElement?.focus();
	}

	function processExtractedVideo(video: any) {
		const processKey = `${video.originalUrl}-${video.quality}`;
		if ($processingVideos.has(processKey)) return;

		processVideo(video.originalUrl, video.quality, video.extension);
	}

	function isVideoProcessing(video: any): boolean {
		const processKey = `${video.originalUrl}-${video.quality}`;
		return $processingVideos.has(processKey);
	}

	// Clear functions
	function clearProcessedVideosList() {
		clearProcessedVideos();
		processedVideoPreviewStates.clear();
		processedVideoPreviewStates = new Map(processedVideoPreviewStates);
		addLog('Processed videos cleared', 'info');
	}

	function clearExtractedVideosList() {
		clearExtractedVideoData();
		addLog('Extracted videos cleared', 'info');
	}
</script>

<!-- Header Section -->
{#snippet headerSection()}
	<header class="mb-8 text-center">
		<div
			class="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500 to-purple-600 shadow-lg"
		>
			<Link2 class="h-8 w-8 text-white" />
		</div>
		<h1 class="text-4xl font-bold text-zinc-900 dark:text-zinc-100">DirectLinker</h1>
		<p class="mt-2 text-base text-zinc-600 dark:text-zinc-400">
			Convert video URLs to direct download links
		</p>
	</header>
{/snippet}

<!-- Status Header -->
{#snippet statusHeader()}
	<div class="mb-4 flex items-center justify-between">
		<div class="flex items-center gap-2">
			<FileVideo class="h-4 w-4 text-zinc-600 dark:text-zinc-400" />
			<span class="text-sm font-medium text-zinc-900 dark:text-zinc-100">Video Processor</span>
		</div>
		<div class="flex items-center gap-3">
			{#if isOperationRunning}
				<div class="flex items-center gap-1 rounded-md bg-blue-100 px-2 py-1 dark:bg-blue-900/50">
					<Clock class="h-3 w-3 text-blue-600 dark:text-blue-400" />
					<span class="font-mono text-xs text-blue-600 dark:text-blue-400">
						{formatTimer(timer)}
					</span>
				</div>
			{/if}
			<div class="h-2 w-2 rounded-full {operationStatusColor()}"></div>
		</div>
	</div>
{/snippet}

<!-- Input Form -->
{#snippet inputForm()}
	<div class="space-y-4">
		<div class="flex gap-2">
			<div class="relative flex-1">
				<Link2 class="absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-zinc-500" />
				<Input
					id="video-url"
					bind:this={inputElement}
					bind:value={$videoUrl}
					placeholder="Paste video URL here..."
					class="pl-10"
					disabled={isOperationRunning}
					onkeypress={handleKeyPress}
				/>
			</div>
			<Button
				variant="outline"
				size="icon"
				onclick={clearInput}
				disabled={!$videoUrl || isOperationRunning}
				class="shrink-0"
			>
				<Trash2 class="h-4 w-4" />
			</Button>
		</div>

		<div class="flex flex-col gap-2 md:flex-row">
			<Button
				onclick={() => processVideo()}
				disabled={!$videoUrl.trim() || isOperationRunning}
				class="flex-1"
			>
				{#if $processing}
					<Loader2 class="mr-2 h-4 w-4 animate-spin" />
					Processing...
				{:else}
					<Play class="mr-2 h-4 w-4" />
					Process Video
				{/if}
			</Button>

			<Button
				onclick={extractVideos}
				disabled={!$videoUrl.trim() || isOperationRunning}
				variant="outline"
				class="flex-1"
			>
				{#if $extracting}
					<Loader2 class="mr-2 h-4 w-4 animate-spin" />
					Extracting...
				{:else}
					<List class="mr-2 h-4 w-4" />
					Extract Videos
				{/if}
			</Button>
		</div>
	</div>
{/snippet}

<!-- Error Display -->
{#snippet errorDisplay()}
	{#if anyError}
		<div
			class="my-3 rounded-lg border border-red-200 bg-red-50 p-4 dark:border-red-800 dark:bg-red-900/20"
		>
			<div class="flex items-start gap-3">
				<AlertCircle class="h-5 w-5 shrink-0 text-red-500" />
				<div class="min-w-0 flex-1">
					<h3 class="text-sm font-medium text-red-800 dark:text-red-200">
						{hasError ? 'Processing Failed' : 'Extraction Failed'}
					</h3>
					<p class="mt-1 text-xs text-red-700 dark:text-red-300">{anyError}</p>
					<Button
						onclick={resetAllState}
						variant="outline"
						size="sm"
						class="mt-3 border-red-300 text-red-700 hover:bg-red-100 dark:border-red-700 dark:text-red-200"
					>
						Dismiss
					</Button>
				</div>
			</div>
		</div>
	{/if}
{/snippet}

<!-- Action Buttons Component -->
{#snippet actionButtons(video, type, index = '')}
	<div
		class="flex shrink-0 items-center rounded-md border bg-zinc-50 p-0.5 dark:border-zinc-600 dark:bg-zinc-700"
	>
		<!-- Preview Toggle Button -->
		<Button
			size="icon"
			variant="ghost"
			class="h-7 w-7 {type === 'extracted'
				? $previewStates.get(video.id)
					? 'bg-blue-100 text-blue-500 hover:bg-blue-200 dark:bg-blue-900/50 hover:dark:bg-blue-900'
					: ''
				: isProcessedVideoPreviewOpen(video.id)
					? 'bg-green-100 text-green-500 hover:bg-green-200 dark:bg-green-900/50 hover:dark:bg-green-900'
					: ''}"
			onclick={() => {
				if (type === 'extracted') {
					togglePreview(video.id);
				} else {
					toggleProcessedVideoPreview(video.id);
				}
			}}
			title="Toggle preview"
		>
			<Eye class="h-4 w-4" />
		</Button>

		{#if type === 'extracted' && !video.isHLS}
			<Button
				size="icon"
				variant="ghost"
				class="h-7 w-7 {isVideoProcessing(video) ? 'animate-pulse' : ''}"
				onclick={() => processExtractedVideo(video)}
				disabled={isVideoProcessing(video) || isOperationRunning}
				title="Process this format"
			>
				{#if isVideoProcessing(video)}
					<Loader2 class="h-4 w-4 animate-spin" />
				{:else}
					<Play class="h-4 w-4" />
				{/if}
			</Button>
		{/if}

		<Button
			size="icon"
			variant="ghost"
			class="h-7 w-7 {$copySuccess === `${type}-${video.id || index}` ? 'text-green-500' : ''}"
			disabled={$copySuccess === `${type}-${video.id || index}`}
			onclick={() => copyToClipboard(video.downloadUrl, `${type}-${video.id || index}`)}
			title="Copy link"
		>
			{#if $copySuccess === `${type}-${video.id || index}`}
				<Check class="h-4 w-4" />
			{:else}
				<Copy class="h-4 w-4" />
			{/if}
		</Button>

		{#if type === 'processed' || !video.isHLS}
			<a href={video.downloadUrl} download={video.filename} title="Download video">
				<Button size="icon" variant="ghost" class="h-7 w-7">
					<Download class="h-4 w-4" />
				</Button>
			</a>
		{/if}
	</div>
{/snippet}

<!-- Video Info Display -->
{#snippet videoInfo(video, type)}
	<div class="min-w-0 flex-1">
		{#if type === 'extracted'}
			<!-- Detailed info for extracted videos -->
			<div class="flex items-center gap-2 text-sm">
				<span class="font-medium text-blue-900 dark:text-blue-100">
					{safeGet(video, 'id')}
				</span>
				{#if video?.isHLS}
					<span
						class="rounded bg-orange-100 px-1 py-0.5 text-[12px] text-orange-800 dark:bg-orange-900/50 dark:text-orange-200"
					>
						HLS
					</span>
				{:else}
					<span
						class="rounded bg-orange-100 px-1 py-0.5 text-[12px] text-orange-800 dark:bg-orange-900/50 dark:text-orange-200"
					>
						{safeGet(video, 'extension').toUpperCase()}
					</span>
				{/if}
			</div>
		{:else}
			<!-- Simple info for processed videos - only title/name -->
			<div class="flex items-center gap-2 text-sm">
				<span class="font-medium text-green-900 dark:text-green-100">
					{safeGet(video, 'filename')}
				</span>
			</div>
		{/if}
	</div>
{/snippet}

<!-- Video Item Card -->
{#snippet videoCard(video, type, index = '')}
	<div class="h-full w-full rounded-lg border bg-white p-2 shadow-sm md:p-3 dark:bg-zinc-800">
		<div class="flex items-center justify-between gap-3 sm:items-center">
			{@render videoInfo(video, type)}
			{@render actionButtons(video, type, index)}
		</div>

		{#if (type === 'extracted' && $previewStates.get(video.id)) || (type === 'processed' && isProcessedVideoPreviewOpen(video.id))}
			<div class="mt-3 ">
				<VideoPlayer src={video.downloadUrl} poster={video?.thumbnail} />
			</div>
		{/if}
	</div>
{/snippet}

<!-- Video Section -->
{#snippet videoSection(videos, title, type, colorClass)}
	{#if videos.length > 0}
		<div class="my-3 rounded-lg {colorClass}">
			<div class="mb-3 flex items-center justify-between">
				<h3 class="text-sm font-medium">
					{title} ({videos.length})
				</h3>

				<!-- Clear Button -->
				<Button
					size="sm"
					variant="outline"
					onclick={type === 'processed' ? clearProcessedVideosList : clearExtractedVideosList}
					class="mr-1 text-xs "
					title="Clear all {type} videos"
				>
					<Trash2 class="h-3 w-3" />
				</Button>
			</div>

			<div class="space-y-3 overflow-y-auto pr-1">
				{#each videos as video, index}
					{@render videoCard(video, type, index)}
				{/each}
			</div>
		</div>
	{/if}
{/snippet}

<!-- Instructions -->
{#snippet instructionsSection()}
	<div
		class="mt-6 rounded-lg border border-blue-200 bg-blue-50 p-4 dark:border-blue-800 dark:bg-blue-900/20"
	>
		<h2 class="mb-2 text-sm font-medium text-blue-900 dark:text-blue-100">How to use:</h2>
		<ol class="space-y-1 text-xs text-blue-800 dark:text-blue-200">
			<li><strong>1.</strong> Paste a video page URL and click "Extract Videos".</li>
			<li>
				<strong>2.</strong> Preview Videos with <Eye class="inline h-3 w-3" /> or process specific Videos
				with <Play class="inline h-3 w-3" />.
			</li>
			<li>
				<strong>3.</strong> Copy links with <Copy class="inline h-3 w-3" /> or download with <Download
					class="inline h-3 w-3"
				/>.
			</li>
			<li>
				<strong>4.</strong> Processed videos persist across sessions and show preview by default.
			</li>
		</ol>
	</div>
{/snippet}

<!-- Floating Actions -->
{#snippet floatingActions()}
	{#if $processedVideos.length > 0 || isOperationRunning}
		<div class="fixed right-6 bottom-6 z-40 flex flex-col gap-2">
			{#if isOperationRunning}
				<Button
					size="icon"
					variant="destructive"
					onclick={cancelOperation}
					class="h-10 w-10 rounded-full shadow-lg"
					title="Cancel Operation"
				>
					<X class="h-4 w-4" />
				</Button>
			{/if}

			{#if $processedVideos.length > 0}
				<Button
					size="icon"
					onclick={() => copyToClipboard($processedVideos[0]?.downloadUrl || '', 'float')}
					class="h-10 w-10 rounded-full shadow-lg {$copySuccess === 'float'
						? 'bg-green-700'
						: 'bg-green-600'} hover:bg-green-700"
					disabled={$copySuccess === 'float'}
					title="Copy latest video link"
				>
					{#if $copySuccess === 'float'}
						<Check class="h-4 w-4" />
					{:else}
						<Copy class="h-4 w-4" />
					{/if}
				</Button>
			{/if}
		</div>
	{/if}
{/snippet}

<svelte:head>
	<title>DirectLinker - Video URL to Direct Download</title>
	<meta name="description" content="Convert video URLs to direct download links" />
</svelte:head>

<main class="container mx-auto max-w-4xl px-2 py-6 md:px-4">
	{@render headerSection()}

	<section class="mx-auto">
		<div
			class="rounded-lg border bg-white p-3 shadow-sm md:p-6 dark:border-zinc-700 dark:bg-zinc-800"
		>
			{@render statusHeader()}
			{@render inputForm()}
			{@render errorDisplay()}

			{@render videoSection($processedVideos, 'Processed Videos', 'processed', '')}

			{@render videoSection(extractedVideos, 'extracted Videos', 'extracted', '')}
		</div>

		{@render instructionsSection()}
	</section>

	{@render floatingActions()}
</main>
