import { json } from '@sveltejs/kit';
import { SERVER_BASE_URL } from '$env/static/private';
import { env } from '$env/dynamic/private';
import { logger } from '$lib/server/logger.js';
import type { RequestHandler } from './$types.js';

interface ExtractVideosRequest {
	url: string;
}

interface VideoFormat {
	format_id: string;
	format: string;
	url?: string;
	manifest_url?: string;
	thumbnail?: string;
	resolution?: string;
	width?: number;
	height?: number;
	filesize?: number;
	ext: string;
	protocol: string;
	http_headers?: Record<string, string>;
}

interface ServerResponse {
	success: boolean;
	video?: {
		duration: number;
		formats: VideoFormat[];
	};
	error?: string;
}

interface ProcessedFormat {
	id: string;
	quality: string;
	thumbnail: string;
	resolution?: string;
	width?: number;
	height?: number;
	fileSize: number | null;
	extension: string;
	protocol: string;
	originalUrl: string;
	downloadUrl: string;
	isHLS: boolean;
}

interface ExtractVideosResponse {
	success: boolean;
	video?: {
		duration: number;
		formats: ProcessedFormat[];
		totalFormats: number;
	};
	error?: string;
	details?: string;
}

// Configuration constants
const DEFAULT_SERVER_URL = 'http://localhost:8000';
const REQUEST_TIMEOUT = 500000; // 500 seconds

// Validation functions
function validateUrl(url: string): void {
	if (!url || typeof url !== 'string' || !url.trim()) {
		throw new Error('URL is required');
	}

	try {
		new URL(url);
	} catch {
		throw new Error('Invalid URL format');
	}
}

async function parseRequestBody(request: Request): Promise<ExtractVideosRequest> {
	try {
		const body = await request.json();

		if (!body || typeof body !== 'object') {
			throw new Error('Invalid request body');
		}

		return {
			url: body.url
		};
	} catch (error) {
		const errorMessage = error instanceof Error ? error.message : 'Failed to parse request body';
		throw new Error(`Invalid request format: ${errorMessage}`);
	}
}

// Server communication
function getServerUrl(): string {
	return SERVER_BASE_URL || DEFAULT_SERVER_URL;
}

async function fetchFromServer(url: string): Promise<ServerResponse> {
	const serverUrl = getServerUrl();

	logger.info(`Forwarding request to processing server: ${serverUrl}`);
	logger.info(`Extracting videos from: ${url}`);

	try {
		const response = await fetch(`${serverUrl}/extract-videos`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json'
			},
			body: JSON.stringify({ url }),
			signal: AbortSignal.timeout(REQUEST_TIMEOUT)
		});

		if (!response.ok) {
			const errorData = (await response.json().catch(() => ({}))) as { error?: string };
			logger.error('Processing server error:', errorData);
			throw new Error(errorData.error || `Processing server error: ${response.status}`);
		}

		const data = (await response.json()) as ServerResponse;

		if (!data.success || !data.video || !data.video.formats) {
			throw new Error('Invalid response format from processing server');
		}

		return data;
	} catch (error) {
		if (error instanceof Error) {
			throw error;
		}
		throw new Error('Unknown error occurred while fetching from processing server');
	}
}

// Format processing
function createProxyUrl(videoUrl: string, userAgent: string): string {
	const encodedUrl = encodeURIComponent(videoUrl);
	const encodedUserAgent = encodeURIComponent(userAgent);
	const clientUrl = env.CLIENT_BASE_URL || '';

	return `${clientUrl}/api/proxy-video?url=${encodedUrl}&userAgent=${encodedUserAgent}`;
}

function processVideoFormat(format: VideoFormat, index: number): ProcessedFormat {
	logger.debug(`Processing format ${index + 1}:`, {
		format_id: format.format_id,
		resolution: format.resolution,
		quality: format.format,
		protocol: format.protocol
	});

	const videoUrl = format.url || format.manifest_url || '';
	const userAgent = format.http_headers?.['User-Agent'] || '';
	const proxyUrl = createProxyUrl(videoUrl, userAgent);

	return {
		id: format.format_id,
		quality: format.format,
		thumbnail: format.thumbnail || '',
		resolution: format.resolution,
		width: format.width,
		height: format.height,
		fileSize: format.filesize || null,
		extension: format.ext,
		protocol: format.protocol,
		originalUrl: videoUrl,
		downloadUrl: proxyUrl,
		isHLS: format.protocol === 'm3u8_native'
	};
}

function processVideoFormats(formats: VideoFormat[]): ProcessedFormat[] {
	return formats.map((format, index) => processVideoFormat(format, index));
}

// Response builders
function createSuccessResponse(duration: number, processedFormats: ProcessedFormat[]): Response {
	logger.success(`Found ${processedFormats.length} video formats`);

	const response: ExtractVideosResponse = {
		success: true,
		video: {
			duration,
			formats: processedFormats,
			totalFormats: processedFormats.length
		}
	};

	return json(response);
}

function createErrorResponse(error: Error): Response {
	logger.error('Error in video extraction:', error.message);

	if (error.name === 'AbortError') {
		const response: ExtractVideosResponse = {
			success: false,
			error: 'Request timeout - video extraction took too long'
		};
		return json(response, { status: 408 });
	}

	if (isConnectionError(error)) {
		const response: ExtractVideosResponse = {
			success: false,
			error:
				'Cannot connect to video processing server. Make sure the processing server is running.',
			details: 'Start the processing server'
		};
		return json(response, { status: 503 });
	}

	if (isValidationError(error)) {
		const response: ExtractVideosResponse = {
			success: false,
			error: error.message
		};
		return json(response, { status: 400 });
	}

	const response: ExtractVideosResponse = {
		success: false,
		error: error.message || 'Internal server error'
	};
	return json(response, { status: 500 });
}

// Error type checking
function isConnectionError(error: Error): boolean {
	return (
		error.message.includes('fetch') ||
		error.message.includes('ECONNREFUSED') ||
		error.message.includes('connect')
	);
}

function isValidationError(error: Error): boolean {
	return (
		error.message.includes('URL is required') ||
		error.message.includes('Invalid URL format') ||
		error.message.includes('Invalid request')
	);
}

// Main processing function
async function extractVideos(
	url: string
): Promise<{ duration: number; processedFormats: ProcessedFormat[] }> {
	const data = await fetchFromServer(url);
	const processedFormats = processVideoFormats(data.video!.formats);

	return {
		duration: data.video!.duration,
		processedFormats
	};
}

// Main request handler
export const POST: RequestHandler = async ({ request }) => {
	try {
		// Parse and validate request
		const requestData = await parseRequestBody(request);
		validateUrl(requestData.url);

		// Extract videos
		const { duration, processedFormats } = await extractVideos(requestData.url);

		// Return success response
		return createSuccessResponse(duration, processedFormats);
	} catch (error) {
		// Handle all errors consistently
		const err = error instanceof Error ? error : new Error('Unknown error occurred');
		return createErrorResponse(err);
	}
};
