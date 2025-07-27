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
		result,
		addLog,
		resetProgress,
		processedVideos,
		addProcessedVideo
	} from '$lib/stores/videoStore';

	// Component State
	let inputElement: HTMLInputElement | undefined | any;
	let abortController: AbortController | null = $state(null);
	let copySuccess = $state('');
	let extractedVideos = $state<
		{
			quality: string;
			format: string;
			filesize: string;
			resolution: string;
			duration: string;
			downloadUrl: string;
			previewUrl?: string;
			filename: string;
		}[]
	>([]);
	let extracting = $state(false);
	let showExtracted = $state(false);
	let extractionError = $state<string | null>(null);
	let processingVideos = $state<Set<string>>(new Set());
	let previewStates = $state<Map<number, boolean>>(new Map());
	let timer = $state(0);
	let timerInterval: NodeJS.Timeout | null = null;

	// Derived State for
	let isOperationRunning = $derived($processing || extracting);
	let hasError = $derived($result?.error);
	let anyError = $derived(hasError || extractionError);

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
		timerInterval = setInterval(() => {
			timer++;
		}, 1000);
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

	// Core Logic
	function resetOperationState() {
		result.set(null);
		extractionError = null;
		resetProgress();
		copySuccess = '';
	}

	async function processVideo(url?: string) {
		const targetUrl = url || $videoUrl.trim();
		if (!targetUrl || isOperationRunning) return;

		const processId = `process_${Date.now()}`;
		if (url) {
			processingVideos.add(url);
			processingVideos = new Set(processingVideos);
		}

		abortController = new AbortController();
		processing.set(true);
		if (!url) resetOperationState();
		startTimer();

		try {
			const response = await fetch('/api/process-video', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ userVideoUrl: targetUrl }),
				signal: abortController.signal
			});

			if (abortController.signal.aborted) return;

			const data = await response.json();
			if (data.success) {
				const processedVideo = {
					id: processId,
					originalUrl: targetUrl,
					filename: data.filename || 'video.mp4',
					downloadUrl: data.downloadUrl,
					videoSrc: data.downloadUrl,
					processedAt: new Date().toISOString(),
					quality: extractedVideos.find((v) => v.downloadUrl === targetUrl)?.quality || 'Unknown',
					format: extractedVideos.find((v) => v.downloadUrl === targetUrl)?.format || 'Unknown',
					filesize: extractedVideos.find((v) => v.downloadUrl === targetUrl)?.filesize || 'Unknown'
				};

				addProcessedVideo(processedVideo);
				addLog('Video processed successfully!', 'success');
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
				processingVideos.delete(url);
				processingVideos = new Set(processingVideos);
			}
		}
	}

	async function extractVideos() {
		const url = $videoUrl.trim();
		if (!url || isOperationRunning) return;

		abortController = new AbortController();
		extracting = true;
		resetOperationState();
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
			if (data.success) {
				extractedVideos = data.videos;
				showExtracted = true;
				previewStates = new Map(data.videos.map((_, index) => [index, true]));
				addLog(`Found ${data.videos.length} video formats!`, 'success');
			} else {
				throw new Error(data.error || 'Extraction failed');
			}
		} catch (error: any) {
			if (error.name === 'AbortError') {
				addLog('Operation cancelled', 'info');
			} else {
				extractionError = error.message;
				addLog(`Error: ${error.message}`, 'error');
			}
		} finally {
			extracting = false;
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

	function togglePreview(index: number) {
		const currentState = previewStates.get(index) ?? true;
		previewStates.set(index, !currentState);
		previewStates = new Map(previewStates);
	}

	// UI Handlers
	async function copyToClipboard(text: string, id = '') {
		try {
			await navigator.clipboard.writeText(text);
			copySuccess = id;
			addLog('Link copied!', 'info');

			setTimeout(() => {
				if (copySuccess === id) copySuccess = '';
			}, 2000);
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
		resetOperationState();
		inputElement?.focus();
	}

	function removeProcessedVideo(id: string) {
		processedVideos.update((videos) => videos.filter((v) => v.id !== id));
	}
</script>

<!-- Header Snippet -->
{#snippet headerSection()}
	<header class="mb-8 text-center">
		<div
			class="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500 to-purple-600 shadow-lg sm:h-16 sm:w-16"
		>
			<Link2 class="h-6 w-6 text-white sm:h-8 sm:w-8" />
		</div>
		<h1 class="text-2xl font-bold text-zinc-900 sm:text-4xl dark:text-zinc-100">DirectLinker</h1>
		<p class="mt-2 text-sm text-zinc-600 sm:text-base dark:text-zinc-400">
			Convert video URLs to direct download links
		</p>
	</header>
{/snippet}

<!-- Status Header Snippet -->
{#snippet statusHeader()}
	<div class="mb-4 flex items-center justify-between">
		<div class="flex items-center gap-2">
			<FileVideo class="h-4 w-4 text-zinc-600 dark:text-zinc-400" />
			<span class="text-sm font-medium text-zinc-900 dark:text-zinc-100">Video Processor</span>
		</div>
		<div class="flex items-center gap-3">
			<!-- Timer -->
			{#if isOperationRunning}
				<div class="flex items-center gap-1 rounded-md bg-blue-100 px-2 py-1 dark:bg-blue-900/50">
					<Clock class="h-3 w-3 text-blue-600 dark:text-blue-400" />
					<span class="font-mono text-xs text-blue-600 dark:text-blue-400">
						{formatTimer(timer)}
					</span>
				</div>
			{/if}
			<!-- Operation Status Dot -->
			<div class="h-2 w-2 rounded-full {operationStatusColor()}"></div>
		</div>
	</div>
{/snippet}

<!-- Input Form Snippet -->
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
					class="focus: pl-10"
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
				aria-label="Clear input"
			>
				<Trash2 class="h-4 w-4" />
			</Button>
		</div>

		<!-- Action Buttons -->
		<div class="mb-4 flex flex-col gap-2 md:flex-row">
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
				{#if extracting}
					<Loader2 class="mr-2 h-4 w-4 animate-spin" />
					Extracting...
				{:else}
					<List class="mr-2 h-4 w-4" />
					Extract Formats
				{/if}
			</Button>
		</div>
	</div>
{/snippet}

<!-- Error Display Snippet -->
{#snippet errorDisplay()}
	{#if anyError}
		<div
			class="mb-3 rounded-lg border border-red-200 bg-red-50 p-4 dark:border-red-800 dark:bg-red-900/20"
		>
			<div class="flex items-start gap-3">
				<AlertCircle class="h-5 w-5 shrink-0 text-red-500" />
				<div class="min-w-0 flex-1">
					<h3 class="text-sm font-medium text-red-800 dark:text-red-200">
						{hasError ? 'Processing Failed' : 'Extraction Failed'}
					</h3>
					<p class="mt-1 text-xs text-red-700 dark:text-red-300">{anyError}</p>
					<Button
						onclick={resetOperationState}
						variant="outline"
						size="sm"
						class="mt-3 border-red-300 text-red-700 hover:bg-red-100 dark:border-red-700 dark:text-red-200 dark:hover:bg-red-900/30"
					>
						Dismiss
					</Button>
				</div>
			</div>
		</div>
	{/if}
{/snippet}

<!-- Processed Video Item Snippet -->
{#snippet processedVideoItem(video)}
	<div
		class="rounded-lg border border-green-300 bg-white p-3 shadow-sm dark:border-green-600 dark:bg-zinc-800"
	>
		<!-- Main card content: Info + Actions -->
		<div class="flex items-start justify-between gap-3 sm:items-center">
			<!-- Video Info -->
			<div class="min-w-0 flex-1"></div>

			<!-- Compact Action Buttons -->
			<div
				class="flex shrink-0 items-center rounded-md border bg-zinc-50 p-0.5 dark:border-zinc-600 dark:bg-zinc-700"
			>
				<Button
					size="icon"
					variant="ghost"
					class="h-7 w-7 {copySuccess === `processed-${video.id}` ? 'text-green-500' : ''}"
					aria-label="Copy link"
					title="Copy link"
					disabled={copySuccess === `processed-${video.id}`}
					onclick={() => copyToClipboard(video.downloadUrl, `processed-${video.id}`)}
				>
					{#if copySuccess === `processed-${video.id}`}
						<Check class="h-4 w-4" />
					{:else}
						<Copy class="h-4 w-4" />
					{/if}
				</Button>
				<a href={video.downloadUrl} download={video.filename} title="Download video">
					<Button size="icon" variant="ghost" class="h-7 w-7">
						<Download class="h-4 w-4" />
					</Button>
				</a>
				<Button
					size="icon"
					variant="ghost"
					class="h-7 w-7 text-red-500 hover:text-red-700"
					aria-label="Remove"
					title="Remove from list"
					onclick={() => removeProcessedVideo(video.id)}
				>
					<X class="h-4 w-4" />
				</Button>
			</div>
		</div>

		<!-- Default Open Preview Player -->
		{#if video.downloadUrl}
			<div class="mt-3 w-full rounded-lg border bg-black dark:border-zinc-700">
				<VideoPlayer src={video.downloadUrl} poster={video.thumbnail} />
			</div>
		{/if}
	</div>
{/snippet}

<!-- Processed Videos Section Snippet -->
{#snippet processedVideosSection()}
	{#if $processedVideos.length > 0}
		<div
			class="rounded-lg border border-green-200 bg-green-50 p-4 dark:border-green-800 dark:bg-green-900/20"
		>
			<h3 class="mb-3 text-sm font-medium text-green-800 dark:text-green-200">
				Processed Videos ({$processedVideos.length})
			</h3>

			<div class="max-h-96 space-y-3 overflow-y-auto pr-1">
				{#each $processedVideos as video (`processed-${video.id}`)}
					{@render processedVideoItem(video)}
				{/each}
			</div>
		</div>
	{/if}
{/snippet}

<!-- Extracted Video Item Snippet -->
{#snippet extractedVideoItem(video, index)}
	<div
		class="rounded-lg border border-blue-300 bg-white p-3 shadow-sm transition-all duration-200 dark:border-blue-600 dark:bg-zinc-800"
	>
		<!-- Main card content: Info + Actions -->
		<div class="flex items-start justify-between gap-3 sm:items-center">
			<!-- Video Info -->
			<div class="min-w-0 flex-1">
				<div class="flex items-center gap-2 text-sm">
					<span class="font-medium text-blue-900 dark:text-blue-100">
						{video.quality || 'N/A'}
					</span>
					<span class="text-xs text-zinc-600 dark:text-zinc-400">
						{video.format} • {video.filesize}
					</span>
				</div>
				<p class="truncate text-xs text-zinc-700 dark:text-zinc-300">
					{video.resolution} • {video.duration}
				</p>
			</div>

			<!-- Compact Action Buttons - Only Preview and Copy -->
			<div
				class="flex shrink-0 items-center rounded-md border bg-zinc-50 p-0.5 dark:border-zinc-600 dark:bg-zinc-700"
			>
				<Button
					size="icon"
					variant="ghost"
					class="h-7 w-7 {previewStates.get(index)
						? 'bg-blue-100 text-blue-500 dark:bg-blue-900/50'
						: ''}"
					aria-label="Preview this video"
					title="Preview this video"
					onclick={() => togglePreview(index)}
				>
					<Eye class="h-4 w-4" />
				</Button>
				<Button
					size="icon"
					variant="ghost"
					class="h-7 w-7 {copySuccess === `video-${index}` ? 'text-green-500' : ''}"
					aria-label="Copy link"
					title="Copy link"
					disabled={copySuccess === `video-${index}`}
					onclick={() => copyToClipboard(video.downloadUrl, `video-${index}`)}
				>
					{#if copySuccess === `video-${index}`}
						<Check class="h-4 w-4" />
					{:else}
						<Copy class="h-4 w-4" />
					{/if}
				</Button>
			</div>
		</div>
		<!-- Item-specific preview with proper spacing -->
		{#if previewStates.get(index)}
			<div class="mt-3 w-full rounded-lg border bg-black dark:border-zinc-700">
				<VideoPlayer src={video.downloadUrl} poster={video.thumbnail} />
			</div>
		{/if}
	</div>
{/snippet}

<!-- Extracted Videos Section Snippet -->
{#snippet extractedVideosSection()}
	{#if showExtracted && extractedVideos.length > 0}
		<div
			class="rounded-lg border border-blue-200 bg-blue-50 p-4 dark:border-zinc-800 dark:bg-zinc-900/20"
		>
			<div class="mb-3 flex items-center justify-between">
				<h3 class="text-sm font-medium text-blue-800 dark:text-blue-200">
					Available Formats ({extractedVideos.length})
				</h3>
			</div>

			<div class="max-h-96 space-y-3 overflow-y-auto pr-1">
				{#each extractedVideos as video, index (`video-${index}`)}
					{@render extractedVideoItem(video, index)}
				{/each}
			</div>
		</div>
	{/if}
{/snippet}

<!-- Instructions Snippet -->
{#snippet instructionsSection()}
	<div
		class="mt-6 rounded-lg border border-blue-200 bg-blue-50 p-4 dark:border-blue-800 dark:bg-blue-900/20"
	>
		<h2 class="mb-2 text-sm font-medium text-blue-900 dark:text-blue-100">How to use:</h2>
		<ol class="space-y-1 text-xs text-blue-800 dark:text-blue-200">
			<li><strong>1.</strong> Paste a video page URL and click "Extract Formats".</li>
			<li>
				<strong>2.</strong> From the list, click the <Eye class="inline h-3 w-3" /> button to preview
				a specific format, or use the <Copy class="inline h-3 w-3" /> button to copy the direct link.
			</li>
			<li><strong>3.</strong> Use "Process Video" to convert and download videos.</li>
			<li>
				<strong>4.</strong> Your processed videos are saved and will persist across sessions.
			</li>
		</ol>
	</div>
{/snippet}

<!-- Floating Actions Snippet -->
{#snippet floatingActions()}
	{#if $processedVideos.length > 0 || isOperationRunning || showExtracted}
		<div class="fixed right-4 bottom-4 z-40 flex flex-col gap-2 sm:right-6 sm:bottom-6">
			{#if isOperationRunning}
				<Button
					size="icon"
					variant="destructive"
					onclick={cancelOperation}
					class="h-12 w-12 rounded-full shadow-lg sm:h-10 sm:w-10"
					aria-label="Cancel Operation"
					title="Cancel Operation"
				>
					<X class="h-4 w-4" />
				</Button>
			{/if}

			{#if $processedVideos.length > 0}
				<Button
					size="icon"
					onclick={() => copyToClipboard($processedVideos[0]?.downloadUrl || '', 'float')}
					class="h-12 w-12 rounded-full shadow-lg sm:h-10 sm:w-10 {copySuccess === 'float'
						? 'bg-green-700'
						: 'bg-green-600'} hover:bg-green-700"
					disabled={copySuccess === 'float'}
					aria-label="Copy latest video link"
					title="Copy latest video link"
				>
					{#if copySuccess === 'float'}
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

<main class="container mx-auto max-w-4xl px-4 py-6">
	<!-- Render Header -->
	{@render headerSection()}

	<!-- Main Form -->
	<section class="mx-auto max-w-2xl">
		<div
			class="rounded-lg border bg-white p-4 shadow-sm sm:p-6 dark:border-zinc-700 dark:bg-zinc-800"
		>
			<!-- Render Status Header -->
			{@render statusHeader()}

			<!-- Render Input Form -->
			{@render inputForm()}

			<!-- Render Error Display -->
			{@render errorDisplay()}

			<!-- Render Processed Videos -->
			{@render processedVideosSection()}

			<!-- Render Extracted Videos -->
			{@render extractedVideosSection()}
		</div>

		<!-- Render Instructions -->
		{@render instructionsSection()}
	</section>

	<!-- Render Floating Actions -->
	{@render floatingActions()}
</main>
