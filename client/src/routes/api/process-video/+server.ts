import { json } from '@sveltejs/kit';
import { puppeteerService, type VideoInfo } from '$lib/server/puppeteer.js';
import { logger } from '$lib/server/logger.js';
import type { RequestHandler } from './$types.js';

interface ProcessVideoRequest {
	userVideoUrl: string;
	method?: ProcessingMethod;
	quality?: string;
	format?: string;
}

interface VideoMetadata {
	quality?: string;
	format?: string;
	fileSize?: string;
	duration?: number;
	resolution?: string;
	fps?: number;
	bitrate?: string;
	videoCodec?: string;
	audioCodec?: string;
	thumbnail?: string;
}

interface ProcessedVideoResult {
	success: boolean;
	videoSrc: string;
	downloadUrl: string;
	filename: string;
	quality: string;
	format: string;
	fileSize?: string;
	duration?: number;
	resolution?: string;
	fps?: number;
	bitrate?: string;
	videoCodec?: string;
	audioCodec?: string;
	thumbnail?: string;
	cookies: unknown[];
	userAgent: string;
	method: string;
	videoType: string;
	metadata?: VideoMetadata;
}

interface ApiResponse {
	success: boolean;
	video?: ProcessedVideo;
	error?: string;
	details?: string;
	timestamp?: string;
	processingTime?: number;
	availableMethods?: ProcessingMethod[];
}

interface ProcessedVideo {
	id: string;
	originalUrl: string;
	filename: string;
	downloadUrl: string;
	videoSrc: string;
	processedAt: string;
	quality: string;
	format: string;
	fileSize?: string;
	duration?: number;
	resolution?: string;
	fps?: number;
	bitrate?: string;
	videoCodec?: string;
	audioCodec?: string;
	thumbnail?: string;
	processingTime: number;
	method: string;
}

type ProcessingMethod = 'puppeteer' | 'auto';

// Constants
const SUPPORTED_METHODS: ProcessingMethod[] = ['puppeteer', 'auto'];
const DEFAULT_METHOD: ProcessingMethod = 'auto';

// Validation functions
function validateProcessingMethod(method: ProcessingMethod): void {
	if (!SUPPORTED_METHODS.includes(method)) {
		throw new Error(
			`Invalid processing method. Supported methods: ${SUPPORTED_METHODS.join(', ')}`
		);
	}
}

function validateVideoUrl(url: string): void {
	if (!url || typeof url !== 'string' || !url.trim()) {
		throw new Error('No video URL provided');
	}

	try {
		new URL(url);
	} catch {
		throw new Error('Invalid URL format');
	}
}

async function parseRequestBody(request: Request): Promise<ProcessVideoRequest> {
	try {
		const body = await request.json();

		if (!body || typeof body !== 'object') {
			throw new Error('Invalid request body');
		}

		return {
			userVideoUrl: body.userVideoUrl,
			method: body.method,
			quality: body.quality,
			format: body.format
		};
	} catch (error) {
		const errorMessage = error instanceof Error ? error.message : 'Failed to parse request body';
		throw new Error(`Invalid request format: ${errorMessage}`);
	}
}

// URL creation function
function createDownloadUrl(result: VideoInfo): string {
	const params = new URLSearchParams({
		url: result.videoSrc,
		referer: 'https://online-video-cutter.com/',
		cookies: JSON.stringify(result.cookies),
		userAgent: result.userAgent
	});

	return `/api/proxy-video?${params.toString()}`;
}

// Metadata extraction function
function extractMetadata(result: VideoInfo): VideoMetadata {
	return {
		quality: undefined,
		format: undefined,
		fileSize: result.size,
		duration: undefined,
		resolution: undefined,
		fps: undefined,
		bitrate: undefined,
		videoCodec: undefined,
		audioCodec: undefined,
		thumbnail: undefined
	};
}

// Processing functions
async function processWithPuppeteer(
	userVideoUrl: string,
	options: { quality?: string; format?: string } = {}
): Promise<ProcessedVideoResult> {
	try {
		logger.info('Attempting Puppeteer processing...');
		const result = await puppeteerService.getProcessedVideoInfo(userVideoUrl);

		const downloadUrl = createDownloadUrl(result);
		const metadata = extractMetadata(result);

		return {
			success: true,
			videoSrc: result.videoSrc,
			downloadUrl,
			filename: result.filename || 'video.mp4',
			quality: options.quality || metadata.quality || 'Unknown',
			format: options.format || metadata.format || 'mp4',
			fileSize: metadata.fileSize || result.size,
			duration: metadata.duration,
			resolution: metadata.resolution,
			fps: metadata.fps,
			bitrate: metadata.bitrate,
			videoCodec: metadata.videoCodec,
			audioCodec: metadata.audioCodec,
			thumbnail: metadata.thumbnail,
			cookies: result.cookies,
			userAgent: result.userAgent,
			method: 'puppeteer',
			videoType: 'direct',
			metadata
		};
	} catch (error) {
		const errorMessage = error instanceof Error ? error.message : 'Unknown error';
		logger.warn(`Puppeteer processing failed: ${errorMessage}`);
		throw new Error(`Puppeteer processing failed: ${errorMessage}`);
	}
}

async function processVideo(request: ProcessVideoRequest): Promise<ProcessedVideoResult> {
	const { userVideoUrl, quality, format } = request;
	const method = request.method || DEFAULT_METHOD;

	validateProcessingMethod(method);

	if (method === 'puppeteer' || method === 'auto') {
		return await processWithPuppeteer(userVideoUrl, { quality, format });
	}

	throw new Error(`Unsupported processing method: ${method}`);
}

// Response builder functions
function createSuccessResponse(video: ProcessedVideo): Response {
	const response: ApiResponse = {
		success: true,
		video
	};
	return json(response);
}

function createErrorResponse(
	message: string,
	details?: string,
	status: number = 500,
	processingTime?: number
): Response {
	const response: ApiResponse = {
		success: false,
		error: message,
		details,
		timestamp: new Date().toISOString(),
		processingTime,
		availableMethods: SUPPORTED_METHODS
	};
	return json(response, { status });
}

// Helper function to determine status code
function getErrorStatusCode(errorMessage: string): number {
	return errorMessage.includes('No video URL') || errorMessage.includes('Invalid') ? 400 : 500;
}

// Main request handler
export const POST: RequestHandler = async ({ request }) => {
	const startTime = Date.now();

	try {
		// Parse and validate request
		const requestData = await parseRequestBody(request);
		validateVideoUrl(requestData.userVideoUrl);

		// Log processing details
		logger.info(`Processing video URL: ${requestData.userVideoUrl}`);
		logger.info(`Processing method: ${requestData.method || 'auto'}`);
		if (requestData.quality) logger.info(`Requested quality: ${requestData.quality}`);
		if (requestData.format) logger.info(`Requested format: ${requestData.format}`);

		// Process video
		const result = await processVideo(requestData);

		// Build successful response
		const processingTime = Date.now() - startTime;
		logger.success(`Video processed successfully with ${result.method} in ${processingTime}ms`);

		const processedVideo: ProcessedVideo = {
			id: `processed_${Date.now()}`,
			originalUrl: requestData.userVideoUrl,
			filename: result.filename,
			downloadUrl: result.downloadUrl,
			videoSrc: result.videoSrc,
			processedAt: new Date().toISOString(),
			quality: result.quality,
			format: result.format,
			fileSize: result.fileSize,
			duration: result.duration,
			resolution: result.resolution,
			fps: result.fps,
			bitrate: result.bitrate,
			videoCodec: result.videoCodec,
			audioCodec: result.audioCodec,
			thumbnail: result.thumbnail,
			processingTime,
			method: result.method
		};

		return createSuccessResponse(processedVideo);
	} catch (error) {
		const processingTime = Date.now() - startTime;
		const errorMessage = error instanceof Error ? error.message : 'Unknown error occurred';

		logger.error(`Video processing failed after ${processingTime}ms:`, errorMessage);

		const status = getErrorStatusCode(errorMessage);

		return createErrorResponse('Failed to process the video', errorMessage, status, processingTime);
	}
};
