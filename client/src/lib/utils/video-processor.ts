import {
	videoStore,
	apiCache,
	uiState,
	type ExtractedVideoData,
	type PuppeteerProxiedUrlVideo
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
				videoStore.puppeteerProxyUrlError = errorMessage;
				return { success: false, error: errorMessage };
			}
		} finally {
			videoStore.extracting = false;
			uiState.setLoading('extract', false);
		}
	}

	async puppeteerProxyUrl(
		video: VideoInput,
		options: VideoProcessorOptions = {}
	): Promise<ProcessorResult<PuppeteerProxiedUrlVideo>> {
		const targetUrl = video?.originalUrl || videoStore.inputUrl.trim();
		if (!targetUrl) {
			return { success: false, error: 'Please enter a valid URL' };
		}

		const puppeteerProxyUrlKey = `${targetUrl}-${video?.quality || 'default'}`;
		const loadingKey = `puppeteerProxyUrl-${video?.id || 'direct'}`;

		if (video && video.id) {
			videoStore.puppeteerProxyUrlQueue.add(puppeteerProxyUrlKey);
		} else {
			videoStore.puppeteerProxyingUrl = true;
			videoStore.reset();
		}

		try {
			uiState.setLoading(loadingKey, true);
			const response = await fetch('/api/puppeteer-proxy-video', {
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
				const puppeteerProxiedUrlVideo: PuppeteerProxiedUrlVideo = {
					...data.video,
					status: 'completed',
					originalUrl: targetUrl
				};
				videoStore.addPuppeteerProxiedUrlVideo(puppeteerProxiedUrlVideo);
				return { success: true, data: puppeteerProxiedUrlVideo };
			} else {
				throw new Error(data.error || 'PuppeteerProxyingUrl failed');
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
				videoStore.puppeteerProxyUrlQueue.delete(puppeteerProxyUrlKey);
			} else {
				videoStore.puppeteerProxyingUrl = false;
			}
			uiState.setLoading(loadingKey, false);
		}
	}

	// Utility method to check if a video is currently being puppeteerProxiedUrl
	isVideoPuppeteerProxyUrl(video: VideoInput): boolean {
		const puppeteerProxyUrlKey = `${video.originalUrl}-${video.quality || 'default'}`;
		return videoStore.puppeteerProxyUrlQueue.has(puppeteerProxyUrlKey);
	}

	// Utility method to cancel all operations
	cancelAllOperations(): void {
		videoStore.puppeteerProxyingUrl = false;
		videoStore.extracting = false;
		videoStore.puppeteerProxyUrlQueue.clear();
	}
}

export const videoProcessor = new VideoProcessor();
