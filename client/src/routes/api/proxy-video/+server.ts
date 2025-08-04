import { logger } from '$lib/server/logger.js';
import type { RequestHandler } from './$types.js';

// Type definitions
interface VideoStreamParams {
	url: string;
	referer?: string;
	userAgent?: string;
	cookies?: string;
	download?: boolean;
}

interface CookieObject {
	name: string;
	value: string;
}

interface StreamHeaders {
	[key: string]: string;
}

interface RetryConfig {
	maxRetries: number;
	baseDelay: number;
}

type VideoType = 'hls' | 'dash' | 'direct' | 'hls_fragment';

// Configuration constants
const DEFAULT_USER_AGENT =
	'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36';
const RETRY_CONFIG: RetryConfig = {
	maxRetries: 3,
	baseDelay: 1000
};

// Video type detection
function detectVideoType(url: string): VideoType {
	const urlLower = url.toLowerCase();

	if (urlLower.includes('.m3u8')) return 'hls';
	if (urlLower.includes('.mpd')) return 'dash';
	if (urlLower.includes('.ts') || urlLower.includes('frag')) return 'hls_fragment';

	return 'direct';
}

// URL and origin utilities
function extractOriginFromUrl(url: string): string {
	try {
		return new URL(url).origin;
	} catch {
		return url;
	}
}

function resolveAbsoluteUrl(relativeUrl: string, baseUrl: string): string {
	try {
		const base = new URL(baseUrl);

		if (relativeUrl.startsWith('http')) {
			return relativeUrl;
		}

		if (relativeUrl.startsWith('/')) {
			return `${base.protocol}//${base.host}${relativeUrl}`;
		}

		const basePath = base.pathname.substring(0, base.pathname.lastIndexOf('/') + 1);
		return `${base.protocol}//${base.host}${basePath}${relativeUrl}`;
	} catch {
		logger.warn('Failed to resolve relative URL:', relativeUrl);
		throw new Error(`Unable to resolve URL: ${relativeUrl}`);
	}
}

function extractBaseUrl(request: Request): string {
	const url = new URL(request.url);
	return `${url.protocol}//${url.host}`;
}

// Cookie handling
function parseCookieHeader(cookiesStr: string): string {
	if (!cookiesStr) return '';

	try {
		const cookiesObj = JSON.parse(cookiesStr);

		if (Array.isArray(cookiesObj)) {
			return cookiesObj.map((cookie: CookieObject) => `${cookie.name}=${cookie.value}`).join('; ');
		}

		return cookiesStr;
	} catch {
		logger.debug('Using cookies as raw string');
		return cookiesStr;
	}
}

// Request headers building
function buildStreamHeaders(params: {
	referer: string;
	userAgent: string;
	cookieHeader: string;
	range?: string;
	videoType?: VideoType;
}): StreamHeaders {
	const { referer, userAgent, cookieHeader, range, videoType } = params;
	const origin = extractOriginFromUrl(referer);

	const headers: StreamHeaders = {
		'User-Agent': userAgent,
		Accept: '*/*',
		'Accept-Language': 'en-US,en;q=0.9',
		'Accept-Encoding': 'gzip, deflate, br',
		Connection: 'keep-alive',
		'Cache-Control': 'no-cache',
		Pragma: 'no-cache'
	};

	// Add referer and origin if provided
	if (referer) {
		headers['Referer'] = referer;
		if (origin && origin !== referer) {
			headers['Origin'] = origin;
		}
	}

	// Add cookies if provided
	if (cookieHeader) {
		headers['Cookie'] = cookieHeader;
	}

	// Add range header for partial requests
	if (range) {
		headers['Range'] = range;
	}

	// Video type specific headers
	switch (videoType) {
		case 'hls':
			headers['Accept'] = 'application/vnd.apple.mpegurl, application/x-mpegurl, */*';
			headers['Sec-Fetch-Dest'] = 'empty';
			headers['Sec-Fetch-Mode'] = 'cors';
			headers['Sec-Fetch-Site'] = 'cross-site';
			break;
		case 'hls_fragment':
			headers['Sec-Fetch-Dest'] = 'empty';
			headers['Sec-Fetch-Mode'] = 'cors';
			headers['Sec-Fetch-Site'] = 'cross-site';
			break;
		default:
			headers['Sec-Fetch-Dest'] = 'video';
			headers['Sec-Fetch-Mode'] = 'cors';
			headers['Sec-Fetch-Site'] = 'cross-site';
	}

	return headers;
}

// Filename extraction
function extractFilename(url: string, contentDisposition?: string): string {
	if (contentDisposition) {
		const match = contentDisposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
		if (match?.[1]) {
			return match[1].replace(/['"]/g, '');
		}
	}

	try {
		const urlPath = new URL(url).pathname;
		const urlFilename = urlPath.split('/').pop();

		if (urlFilename && urlFilename.includes('.')) {
			const videoType = detectVideoType(url);
			if (videoType === 'hls_fragment' && url.includes('.ts')) {
				return urlFilename.replace(/\.[^.]+$/, '.ts');
			}
			return urlFilename;
		}
	} catch {
		// Fall through to default
	}

	return 'video.mp4';
}

// HLS playlist rewriting
function rewriteHlsPlaylist(
	playlistContent: string,
	originalUrl: string,
	proxyBaseUrl: string,
	referer: string,
	userAgent: string,
	cookies: string
): string {
	const lines = playlistContent.split('\n');
	const rewrittenLines: string[] = [];

	for (const line of lines) {
		const trimmedLine = line.trim();

		// Skip comments and empty lines
		if (!trimmedLine || trimmedLine.startsWith('#')) {
			rewrittenLines.push(line);
			continue;
		}

		try {
			// Resolve relative URLs to absolute URLs
			const absoluteUrl = resolveAbsoluteUrl(trimmedLine, originalUrl);

			// Create proxy URL
			const proxyUrl = new URL('/api/proxy-video', proxyBaseUrl);
			proxyUrl.searchParams.set('url', encodeURIComponent(absoluteUrl));
			proxyUrl.searchParams.set('referer', referer);
			proxyUrl.searchParams.set('userAgent', userAgent);

			if (cookies) {
				proxyUrl.searchParams.set('cookies', cookies);
			}

			rewrittenLines.push(proxyUrl.toString());
		} catch {
			logger.warn(`Failed to rewrite playlist line: ${trimmedLine}`);
			rewrittenLines.push(line);
		}
	}

	return rewrittenLines.join('\n');
}

// Retry mechanism for fetch requests
async function fetchWithRetry(
	url: string,
	headers: StreamHeaders,
	config: RetryConfig = RETRY_CONFIG
): Promise<Response> {
	let lastError: Error | null = null;

	for (let attempt = 0; attempt < config.maxRetries; attempt++) {
		try {
			const response = await fetch(url, {
				method: 'GET',
				headers
			});

			// Success or partial content
			if (response.ok || response.status === 206) {
				return response;
			}

			// Handle authentication errors by removing security headers
			if (response.status === 403 || response.status === 401) {
				logger.warn(`Access denied (${response.status}), retrying with modified headers`);
				delete headers['Origin'];
				delete headers['Sec-Fetch-Site'];
				delete headers['Sec-Fetch-Mode'];
				delete headers['Sec-Fetch-Dest'];
			}

			throw new Error(`HTTP ${response.status}: ${response.statusText}`);
		} catch (error) {
			lastError = error instanceof Error ? error : new Error('Unknown fetch error');

			if (attempt < config.maxRetries - 1) {
				const delay = config.baseDelay * (attempt + 1);
				logger.info(
					`Fetch attempt ${attempt + 1} failed, retrying in ${delay}ms: ${lastError.message}`
				);
				await new Promise((resolve) => setTimeout(resolve, delay));
			}
		}
	}

	throw lastError || new Error('All fetch attempts failed');
}

// Response header building
function buildResponseHeaders(
	contentType: string,
	acceptRanges: string,
	filename: string,
	forceDownload: boolean,
	videoType: VideoType,
	contentLength?: string,
	contentRange?: string
): StreamHeaders {
	const headers: StreamHeaders = {
		'Content-Type': contentType,
		'Accept-Ranges': acceptRanges,
		'Access-Control-Allow-Origin': '*',
		'Access-Control-Allow-Methods': 'GET, HEAD, OPTIONS',
		'Access-Control-Allow-Headers': 'Range, Content-Type, Authorization',
		'Access-Control-Expose-Headers':
			'Content-Length, Content-Range, Content-Type, Content-Disposition'
	};

	// Cache control based on video type
	if (videoType === 'hls_fragment') {
		headers['Cache-Control'] = 'public, max-age=3600';
	} else {
		headers['Cache-Control'] = 'public, max-age=3600';
	}

	// Content disposition
	headers['Content-Disposition'] = forceDownload
		? `attachment; filename="${filename}"`
		: `inline; filename="${filename}"`;

	// Optional headers
	if (contentLength) {
		headers['Content-Length'] = contentLength;
	}

	if (contentRange) {
		headers['Content-Range'] = contentRange;
	}

	return headers;
}

// Parameter extraction and validation
function extractStreamParams(url: URL): VideoStreamParams {
	const videoUrl = url.searchParams.get('url');

	if (!videoUrl) {
		throw new Error('No video URL provided');
	}

	return {
		url: decodeURIComponent(videoUrl),
		referer: url.searchParams.get('referer') || '',
		userAgent: url.searchParams.get('userAgent') || DEFAULT_USER_AGENT,
		cookies: url.searchParams.get('cookies') || '',
		download: url.searchParams.get('download') === 'true'
	};
}

// Main streaming logic
async function handleVideoStream(params: VideoStreamParams, request: Request): Promise<Response> {
	const {
		url: videoUrl,
		referer = '',
		userAgent = DEFAULT_USER_AGENT,
		cookies = '',
		download = false
	} = params;
	const videoType = detectVideoType(videoUrl);
	const range = request.headers.get('range');

	logger.info(
		`Processing ${download ? 'download' : 'stream'} request for: ${videoUrl.substring(0, 100)}...`
	);
	logger.info(`Detected video type: ${videoType}`);

	// Parse cookies and build headers
	const cookieHeader = parseCookieHeader(cookies);
	const requestHeaders = buildStreamHeaders({
		referer,
		userAgent,
		cookieHeader,
		range: range || undefined,
		videoType
	});

	// Log headers (hide sensitive data)
	const headersForLog = { ...requestHeaders };
	if (headersForLog.Cookie) {
		headersForLog.Cookie = '[REDACTED]';
	}
	logger.debug('Request headers:', headersForLog);

	// Fetch video response with retry
	const response = await fetchWithRetry(videoUrl, requestHeaders);

	// Handle HLS playlist rewriting
	if (videoType === 'hls') {
		const playlistContent = await response.text();
		const baseUrl = extractBaseUrl(request);
		const rewrittenPlaylist = rewriteHlsPlaylist(
			playlistContent,
			videoUrl,
			baseUrl,
			referer,
			userAgent,
			cookies
		);

		logger.info('Rewritten HLS playlist with proxy URLs');

		return new Response(rewrittenPlaylist, {
			status: 200,
			headers: {
				'Content-Type': 'application/vnd.apple.mpegurl',
				'Access-Control-Allow-Origin': '*',
				'Access-Control-Allow-Methods': 'GET, HEAD, OPTIONS',
				'Access-Control-Allow-Headers': 'Range, Content-Type, Authorization',
				'Cache-Control': 'no-cache, no-store, must-revalidate',
				Pragma: 'no-cache',
				Expires: '0'
			}
		});
	}

	// Extract response metadata
	const contentLength = response.headers.get('content-length');
	const contentType = response.headers.get('content-type') || 'video/mp4';
	const contentDisposition = response.headers.get('content-disposition');
	const acceptRanges = response.headers.get('accept-ranges') || 'bytes';
	const contentRange = response.headers.get('content-range');

	const filename = extractFilename(videoUrl, contentDisposition || undefined);

	// Build response headers
	const responseHeaders = buildResponseHeaders(
		contentType,
		acceptRanges,
		filename,
		download,
		videoType,
		contentLength || undefined,
		contentRange || undefined
	);

	// Handle partial content (206)
	if (range && response.status === 206) {
		logger.info(`Streaming partial content: ${contentRange || 'unknown range'}`);
		return new Response(response.body, {
			status: 206,
			headers: responseHeaders
		});
	}

	// Return full content stream
	const contentLengthMB = contentLength
		? `${(parseInt(contentLength) / 1024 / 1024).toFixed(1)} MB`
		: 'Unknown size';

	const action = download ? 'download' : 'stream';
	logger.success(`Starting ${action} of ${filename} (${contentLengthMB})`);

	return new Response(response.body, {
		status: 200,
		headers: responseHeaders
	});
}

// Main GET handler
export const GET: RequestHandler = async ({ url, request }) => {
	try {
		const params = extractStreamParams(url);
		return await handleVideoStream(params, request);
	} catch (error) {
		const errorMessage = error instanceof Error ? error.message : 'Unknown error occurred';

		logger.error('Error processing video request:', errorMessage);

		return new Response(`Error processing video: ${errorMessage}`, {
			status: 500,
			headers: {
				'Access-Control-Allow-Origin': '*',
				'Access-Control-Allow-Methods': 'GET, HEAD, OPTIONS',
				'Access-Control-Allow-Headers': 'Range, Content-Type, Authorization'
			}
		});
	}
};

// OPTIONS handler for CORS preflight requests
export const OPTIONS: RequestHandler = async () => {
	return new Response(null, {
		status: 200,
		headers: {
			'Access-Control-Allow-Origin': '*',
			'Access-Control-Allow-Methods': 'GET, HEAD, OPTIONS',
			'Access-Control-Allow-Headers': 'Range, Content-Type, Authorization',
			'Access-Control-Max-Age': '86400'
		}
	});
};
