import { logger } from '$lib/server/logger.js';
import type { RequestHandler } from './$types.js';

// Default browser user agent for requests
const DEFAULT_USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36';

/**
 * Detects the type of video from URL
 * This helps us handle different video formats appropriately
 */
function getVideoType(url: string) {
	const lower = url.toLowerCase();
	if (lower.includes('.m3u8')) return 'hls'; // HLS playlist
	if (lower.includes('.mpd')) return 'dash'; // DASH manifest
	if (lower.includes('.ts')) return 'hls_fragment'; // HLS video chunk
	return 'direct'; // Regular MP4/WebM video
}

/**
 * Converts relative URLs to absolute URLs
 * Needed for HLS playlists that contain relative paths
 */
function makeAbsoluteUrl(relativeUrl: string, baseUrl: string): string {
	try {
		if (relativeUrl.startsWith('http')) return relativeUrl;

		const base = new URL(baseUrl);

		// Handle root-relative URLs (/path/to/file)
		if (relativeUrl.startsWith('/')) {
			return `${base.origin}${relativeUrl}`;
		}

		// Handle relative URLs (./file or ../file)
		const basePath = base.pathname.substring(0, base.pathname.lastIndexOf('/') + 1);
		return `${base.origin}${basePath}${relativeUrl}`;
	} catch {
		return relativeUrl; // Fallback to original if parsing fails
	}
}

/**
 * Rewrites HLS playlist to proxy all video chunks through our server
 * This ensures CORS headers are properly set for all segments
 */
function rewriteHlsPlaylist(
	content: string,
	originalUrl: string,
	requestUrl: string,
	params: URLSearchParams
): string {
	const lines = content.split('\n');
	const baseUrl = new URL(requestUrl).origin;

	return lines
		.map((line) => {
			const trimmed = line.trim();

			if (!trimmed || trimmed.startsWith('#')) return line;

			// Rewrite video segment URLs to go through our proxy
			const absoluteUrl = makeAbsoluteUrl(trimmed, originalUrl);
			const newParams = new URLSearchParams(params);
			newParams.set('url', absoluteUrl);

			return `${baseUrl}/api/proxy-video?${newParams}`;
		})
		.join('\n');
}

/**
 * Builds headers for the video request
 * Includes authentication, CORS, and video-specific headers
 */
function buildRequestHeaders(params: {
	referer?: string;
	userAgent: string;
	cookies?: string;
	range?: string | null;
	videoType: string;
}): HeadersInit {
	const headers: Record<string, string> = {
		'User-Agent': params.userAgent,
		Accept: '*/*',
		'Accept-Encoding': 'gzip, deflate, br',
		'Cache-Control': 'no-cache'
	};

	// Add referer if provided (some sites require this)
	if (params.referer) {
		headers['Referer'] = params.referer;
		try {
			headers['Origin'] = new URL(params.referer).origin;
		} catch {
			// Ignore if parsing fails
		}
	}

	// Add cookies for authenticated content
	if (params.cookies) {
		try {
			// Handle both JSON array and string format
			const parsed = JSON.parse(params.cookies);
			if (Array.isArray(parsed)) {
				headers['Cookie'] = parsed.map((c) => `${c.name}=${c.value}`).join('; ');
			} else {
				headers['Cookie'] = params.cookies;
			}
		} catch {
			headers['Cookie'] = params.cookies;
		}
	}

	// Add range header for video seeking
	if (params.range) {
		headers['Range'] = params.range;
	}

	// Add video-specific headers for better compatibility
	if (params.videoType === 'hls' || params.videoType === 'hls_fragment') {
		headers['Sec-Fetch-Dest'] = 'empty';
		headers['Sec-Fetch-Mode'] = 'cors';
	}

	return headers;
}

/**
 * Builds response headers with proper CORS and caching
 */
function buildResponseHeaders(options: {
	contentType: string;
	filename: string;
	download: boolean;
	videoType: string;
	contentLength?: string | null;
	contentRange?: string | null;
}): HeadersInit {
	const headers: Record<string, string> = {
		'Content-Type': options.contentType,
		'Access-Control-Allow-Origin': '*',
		'Access-Control-Allow-Methods': 'GET, HEAD, OPTIONS',
		'Access-Control-Allow-Headers': 'Range',
		'Access-Control-Expose-Headers': 'Content-Length, Content-Range',
		'Accept-Ranges': 'bytes'
	};

	// Set caching based on content type
	// Cache fragments longer to reduce bandwidth
	if (options.videoType === 'hls_fragment') {
		headers['Cache-Control'] = 'public, max-age=3600'; // 1 hour cache for segments
	} else if (options.videoType === 'hls') {
		headers['Cache-Control'] = 'no-cache'; // Don't cache playlists
	} else {
		headers['Cache-Control'] = 'public, max-age=600'; // 10 min for regular videos
	}

	// Set download or inline viewing
	headers['Content-Disposition'] = options.download
		? `attachment; filename="${options.filename}"`
		: `inline; filename="${options.filename}"`;

	// Add content length and range if available
	if (options.contentLength) {
		headers['Content-Length'] = options.contentLength;
	}
	if (options.contentRange) {
		headers['Content-Range'] = options.contentRange;
	}

	return headers;
}

/**
 * Extract filename from URL or content-disposition header
 */
function getFilename(url: string, contentDisposition?: string | null): string {
	// Try to get from content-disposition header first
	if (contentDisposition) {
		const match = contentDisposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
		if (match?.[1]) {
			return match[1].replace(/['"]/g, '');
		}
	}

	// Try to get from URL
	try {
		const pathname = new URL(url).pathname;
		const filename = pathname.split('/').pop();
		if (filename && filename.includes('.')) {
			return filename;
		}
	} catch {
		// Ignore if parsing fails
	}

	// Default filename
	return 'video.mp4';
}

// ============================================
// MAIN HANDLER
// ============================================

/**
 * GET handler - Proxies video content with proper headers
 */
export const GET: RequestHandler = async ({ url, request }) => {
	try {
		// Extract parameters from query string
		const videoUrl = url.searchParams.get('url');
		if (!videoUrl) {
			throw new Error('No video URL provided');
		}

		const params = {
			url: decodeURIComponent(videoUrl),
			referer: url.searchParams.get('referer') || undefined,
			userAgent: url.searchParams.get('userAgent') || DEFAULT_USER_AGENT,
			cookies: url.searchParams.get('cookies') || undefined,
			download: url.searchParams.get('download') === 'true'
		};

		// Detect video type and get range header
		const videoType = getVideoType(params.url);
		const range = request.headers.get('range');

		logger.info(`Proxying ${videoType} video: ${params.url.substring(0, 80)}...`);

		// Build request headers
		const headers = buildRequestHeaders({
			referer: params.referer,
			userAgent: params.userAgent,
			cookies: params.cookies,
			range,
			videoType
		});

		// Fetch the video with retry on failure
		let response: Response;
		let retries = 0;
		const maxRetries = 2;

		while (retries <= maxRetries) {
			try {
				response = await fetch(params.url, { headers });

				// Break if successful or partial content
				if (response.ok || response.status === 206) break;

				// If forbidden, try without some headers
				if (response.status === 403 && retries < maxRetries) {
					delete (headers as any)['Origin'];
					delete (headers as any)['Referer'];
					retries++;
					logger.warn(`Retrying without origin/referer headers (attempt ${retries + 1})`);
					continue;
				}

				throw new Error(`HTTP ${response.status}`);
			} catch (error) {
				if (retries >= maxRetries) throw error;
				retries++;
				await new Promise((r) => setTimeout(r, 1000)); // Wait 1 second between retries
			}
		}

		// Special handling for HLS playlists - rewrite URLs
		if (videoType === 'hls') {
			const playlistContent = await response!.text();

			// Create new params without the URL for cleaner rewriting
			const proxyParams = new URLSearchParams();
			if (params.referer) proxyParams.set('referer', params.referer);
			if (params.userAgent) proxyParams.set('userAgent', params.userAgent);
			if (params.cookies) proxyParams.set('cookies', params.cookies);

			const rewritten = rewriteHlsPlaylist(playlistContent, params.url, request.url, proxyParams);

			return new Response(rewritten, {
				status: 200,
				headers: {
					'Content-Type': 'application/vnd.apple.mpegurl',
					'Access-Control-Allow-Origin': '*',
					'Cache-Control': 'no-cache'
				}
			});
		}

		// Extract response info
		const contentType = response!.headers.get('content-type') || 'video/mp4';
		const contentLength = response!.headers.get('content-length');
		const contentRange = response!.headers.get('content-range');
		const contentDisposition = response!.headers.get('content-disposition');

		const filename = getFilename(params.url, contentDisposition);

		// Build response headers
		const responseHeaders = buildResponseHeaders({
			contentType,
			filename,
			download: params.download,
			videoType,
			contentLength,
			contentRange
		});

		// Log successful proxy
		const size = contentLength
			? `${(parseInt(contentLength) / 1024 / 1024).toFixed(1)}MB`
			: 'unknown';
		logger.success(`Proxying ${filename} (${size})`);

		// Return response with appropriate status
		return new Response(response!.body, {
			status: response!.status, // 200 for full content, 206 for partial
			headers: responseHeaders
		});
	} catch (error) {
		const message = error instanceof Error ? error.message : 'Unknown error';
		logger.error('Proxy error:', message);

		return new Response(`Proxy error: ${message}`, {
			status: 500,
			headers: {
				'Access-Control-Allow-Origin': '*'
			}
		});
	}
};

/**
 * OPTIONS handler - Handle CORS preflight requests
 */
export const OPTIONS: RequestHandler = async () => {
	return new Response(null, {
		status: 200,
		headers: {
			'Access-Control-Allow-Origin': '*',
			'Access-Control-Allow-Methods': 'GET, HEAD, OPTIONS',
			'Access-Control-Allow-Headers': 'Range',
			'Access-Control-Max-Age': '86400' // Cache preflight for 24 hours
		}
	});
};
