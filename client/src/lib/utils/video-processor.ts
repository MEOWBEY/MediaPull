import {
	videoStore,
	apiCache,
	uiState,
	type ExtractedVideoData,
	type ProcessedVideo
} from '$lib/stores/app-state.svelte';

interface VideoProcessorOptions {
	useCache?: boolean;
	abortController?: AbortController | null;
}

interface VideoInput {
	originalUrl?: string;
	quality?: string;
	extension?: string;
	id?: string;
}

interface ProcessorResult<T> {
	success: boolean;
	data?: T;
	error?: string;
	cancelled?: boolean;
	fromCache?: boolean;
}

function isValidUrl(string: string): boolean {
	try {
		new URL(string);
		return true;
	} catch {
		return false;
	}
}

class VideoProcessor {
	async extractVideos(
		inputUrl: string,
		options: VideoProcessorOptions = {}
	): Promise<ProcessorResult<ExtractedVideoData>> {
		if (!inputUrl.trim()) {
			return { success: false, error: 'Please enter a valid URL' };
		}
		if (!isValidUrl(inputUrl.trim())) {
			return { success: false, error: 'Invalid URL format' };
		}

		const cacheKey = `extract-${inputUrl.trim()}`;
		const cachedData = apiCache.get<ExtractedVideoData>(cacheKey);
		if (cachedData && options.useCache) {
			videoStore.setExtractedData(cachedData);
			return { success: true, data: cachedData, fromCache: true };
		}

		videoStore.extracting = true;
		videoStore.extractionError = null;
		videoStore.reset();

		try {
			uiState.setLoading('extract', true);
			const response = await fetch('/api/extract-videos', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ url: inputUrl.trim() }),
				signal: options.abortController?.signal
			});

			if (options.abortController?.signal.aborted) {
				return { success: false, cancelled: true };
			}

			const data = await response.json();

			if (data.success && data.video) {
				const extractedData: ExtractedVideoData = {
					...data.video,
					sourceUrl: inputUrl.trim(),
					totalFormats: data.video.formats?.length || 0
				};
				videoStore.setExtractedData(extractedData);
				if (options.useCache) {
					apiCache.set(cacheKey, extractedData, 30 * 60 * 1000);
				}
				return { success: true, data: extractedData };
			} else {
				throw new Error(data.error || 'Extraction failed');
			}
		} catch (error: unknown) {
			if (error instanceof Error && error.name === 'AbortError') {
				return { success: false, cancelled: true };
			} else {
				const errorMessage = error instanceof Error ? error.message : 'Unknown error occurred';
				videoStore.processingError = errorMessage;
				return { success: false, error: errorMessage };
			}
		} finally {
			videoStore.extracting = false;
			uiState.setLoading('extract', false);
		}
	}

	async processVideo(
		video: VideoInput,
		options: VideoProcessorOptions = {}
	): Promise<ProcessorResult<ProcessedVideo>> {
		const targetUrl = video?.originalUrl || videoStore.inputUrl.trim();
		if (!targetUrl) {
			return { success: false, error: 'Please enter a valid URL' };
		}

		const processKey = `${targetUrl}-${video?.quality || 'default'}`;
		const loadingKey = `process-${video?.id || 'direct'}`;

		if (video && video.id) {
			videoStore.processingQueue.add(processKey);
		} else {
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
				signal: options.abortController?.signal
			});

			if (options.abortController?.signal.aborted) {
				return { success: false, cancelled: true };
			}

			const data = await response.json();

			if (data.success && data.video) {
				const processedVideo: ProcessedVideo = {
					...data.video,
					processingTime: data.video.processingTime || 0,
					status: 'completed',
					originalUrl: targetUrl,
					processedAt: Date.now()
				};
				videoStore.addProcessedVideo(processedVideo);
				return { success: true, data: processedVideo };
			} else {
				throw new Error(data.error || 'Processing failed');
			}
		} catch (error: unknown) {
			if (error instanceof Error && error.name === 'AbortError') {
				return { success: false, cancelled: true };
			} else {
				const errorMessage = error instanceof Error ? error.message : 'Unknown error occurred';
				videoStore.extractionError = errorMessage;
				return { success: false, error: errorMessage };
			}
		} finally {
			if (video && video.id) {
				videoStore.processingQueue.delete(processKey);
			} else {
				videoStore.processing = false;
			}
			uiState.setLoading(loadingKey, false);
		}
	}

	// Utility method to check if a video is currently being processed
	isVideoProcessing(video: VideoInput): boolean {
		const processKey = `${video.originalUrl}-${video.quality || 'default'}`;
		return videoStore.processingQueue.has(processKey);
	}

	// Utility method to cancel all operations
	cancelAllOperations(): void {
		videoStore.processing = false;
		videoStore.extracting = false;
		videoStore.processingQueue.clear();
	}
}

export const videoProcessor = new VideoProcessor();
