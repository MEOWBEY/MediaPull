import { logger } from '$lib/server/logger.js';
import type { RequestHandler } from './$types.js';

// Helper function to detect video type
function detectVideoType(url: string): 'hls' | 'dash' | 'direct' | 'hls_fragment' {
	const urlLower = url.toLowerCase();
	if (urlLower.includes('.m3u8')) return 'hls';
	if (urlLower.includes('.mpd')) return 'dash';
	if (urlLower.includes('.ts') || urlLower.includes('frag')) return 'hls_fragment';
	return 'direct';
}

// Helper function to get origin from referer
function getOriginFromReferer(referer: string): string {
	try {
		return new URL(referer).origin;
	} catch {
		return referer;
	}
}

// Helper function to build comprehensive headers
function buildRequestHeaders(
	referer: string,
	userAgent: string,
	cookieHeader: string,
	range?: string
): Record<string, string> {
	const origin = getOriginFromReferer(referer);

	const headers: Record<string, string> = {
		'User-Agent': userAgent,
		Accept: '*/*',
		'Accept-Language': 'en-US,en;q=0.9',
		'Accept-Encoding': 'gzip, deflate, br',
		Connection: 'keep-alive',
		'Sec-Fetch-Dest': 'video',
		'Sec-Fetch-Mode': 'cors',
		'Sec-Fetch-Site': 'cross-site',
		'Cache-Control': 'no-cache',
		Pragma: 'no-cache'
	};

	// Add referer and origin if provided
	if (referer && referer !== '') {
		headers['Referer'] = referer;
		if (origin && origin !== referer) {
			headers['Origin'] = origin;
		}
	}

	// Add cookies if provided
	if (cookieHeader) {
		headers['Cookie'] = cookieHeader;
	}

	// Add range header if provided
	if (range) {
		headers['Range'] = range;
	}

	return headers;
}

// Helper function to determine filename from URL or headers
function getFilename(url: string, contentDisposition?: string): string {
	let filename = 'video.mp4';

	if (contentDisposition) {
		const match = contentDisposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
		if (match?.[1]) {
			filename = match[1].replace(/['"]/g, '');
		}
	} else {
		// Extract from URL
		try {
			const urlPath = new URL(url).pathname;
			const urlFilename = urlPath.split('/').pop();
			if (urlFilename && urlFilename.includes('.')) {
				filename = urlFilename;
			}
		} catch (e) {
			// Keep default filename
		}
	}

	// Handle special video types
	const videoType = detectVideoType(url);
	if (videoType === 'hls_fragment' && url.includes('.ts')) {
		filename = filename.replace(/\.[^.]+$/, '.ts');
	}

	return filename;
}

// Helper function to rewrite HLS playlist URLs
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
		if (line.trim() && !line.startsWith('#')) {
			// This is a URL line that needs to be rewritten
			let targetUrl = line.trim();

			// Handle relative URLs
			if (!targetUrl.startsWith('http')) {
				try {
					const baseUrl = new URL(originalUrl);
					if (targetUrl.startsWith('/')) {
						// Absolute path
						targetUrl = `${baseUrl.protocol}//${baseUrl.host}${targetUrl}`;
					} else {
						// Relative path
						const basePath = baseUrl.pathname.substring(0, baseUrl.pathname.lastIndexOf('/') + 1);
						targetUrl = `${baseUrl.protocol}//${baseUrl.host}${basePath}${targetUrl}`;
					}
				} catch (e) {
					logger.warn('Failed to resolve relative URL:', targetUrl);
					rewrittenLines.push(line);
					continue;
				}
			}

			// Create proxy URL
			const proxyUrl = new URL('/api/download-video', proxyBaseUrl);
			proxyUrl.searchParams.set('url', encodeURIComponent(targetUrl));
			proxyUrl.searchParams.set('referer', referer);
			proxyUrl.searchParams.set('userAgent', userAgent);
			if (cookies) {
				proxyUrl.searchParams.set('cookies', cookies);
			}

			rewrittenLines.push(proxyUrl.toString());
		} else {
			// Keep comment lines and empty lines as-is
			rewrittenLines.push(line);
		}
	}

	return rewrittenLines.join('\n');
}

// Helper function to get base URL from request
function getBaseUrl(request: Request): string {
	const url = new URL(request.url);
	return `${url.protocol}//${url.host}`;
}

export const GET: RequestHandler = async ({ url, request }) => {
	const videoUrl = url.searchParams.get('url');
	const referer = url.searchParams.get('referer') || '';
	const userAgent =
		url.searchParams.get('userAgent') ||
		'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36';
	const cookiesStr = url.searchParams.get('cookies') || '';
	const forceDownload = url.searchParams.get('download') === 'true';

	if (!videoUrl) {
		logger.error('No video URL provided for download');
		return new Response('No video URL provided', { status: 400 });
	}

	const decodedVideoUrl = decodeURIComponent(videoUrl);
	const videoType = detectVideoType(decodedVideoUrl);

	try {
		logger.info(
			`Processing ${forceDownload ? 'download' : 'stream'} request for: ${decodedVideoUrl.substring(0, 100)}...`
		);
		logger.info(`Detected video type: ${videoType}`);

		// Parse cookies
		let cookieHeader = '';
		if (cookiesStr) {
			try {
				const cookiesObj = JSON.parse(cookiesStr);
				if (Array.isArray(cookiesObj)) {
					cookieHeader = cookiesObj.map((c: any) => `${c.name}=${c.value}`).join('; ');
				} else {
					cookieHeader = cookiesStr;
				}
			} catch (e) {
				logger.warn('Failed to parse cookies, using raw string');
				cookieHeader = cookiesStr;
			}
		}

		// Handle range requests for streaming
		const range = request.headers.get('range');
		if (range) {
			logger.debug(`Range request: ${range}`);
		}

		// Build request headers
		const headers = buildRequestHeaders(referer, userAgent, cookieHeader, range);

		// Special handling for different video types
		if (videoType === 'hls_fragment') {
			logger.info('Handling HLS fragment request');
			headers['Sec-Fetch-Dest'] = 'empty';
			headers['Sec-Fetch-Mode'] = 'cors';
		} else if (videoType === 'hls') {
			logger.info('Handling HLS playlist request');
			headers['Accept'] = 'application/vnd.apple.mpegurl, application/x-mpegurl, */*';
		}

		// Log headers for debugging (remove sensitive info)
		const headersForLog = { ...headers };
		if (headersForLog.Cookie) {
			headersForLog.Cookie = '[REDACTED]';
		}
		logger.debug('Request headers:', headersForLog);

		// Fetch with retry logic
		let response: Response;
		let retryCount = 0;
		const maxRetries = 3;

		while (retryCount < maxRetries) {
			try {
				response = await fetch(decodedVideoUrl, {
					headers,
					method: 'GET'
				});

				if (response.ok || response.status === 206) {
					break;
				}

				if (response.status === 403 || response.status === 401) {
					logger.warn(`Access denied (${response.status}), trying without some headers`);
					// Remove potentially problematic headers and retry
					delete headers['Origin'];
					delete headers['Sec-Fetch-Site'];
					delete headers['Sec-Fetch-Mode'];
					delete headers['Sec-Fetch-Dest'];
				}

				retryCount++;
				if (retryCount < maxRetries) {
					logger.info(
						`Retry ${retryCount}/${maxRetries} for ${response.status} ${response.statusText}`
					);
					await new Promise((resolve) => setTimeout(resolve, 1000 * retryCount));
				}
			} catch (fetchError: any) {
				retryCount++;
				if (retryCount >= maxRetries) {
					throw fetchError;
				}
				logger.warn(`Fetch attempt ${retryCount} failed:`, fetchError.message);
				await new Promise((resolve) => setTimeout(resolve, 1000 * retryCount));
			}
		}

		if (!response!.ok && response!.status !== 206) {
			logger.error(
				`Failed to fetch video after ${maxRetries} attempts: ${response!.status} ${response!.statusText}`
			);

			let errorBody = '';
			try {
				errorBody = await response!.text();
			} catch {}

			return new Response(
				`Error fetching video: ${response!.statusText}${errorBody ? ` - ${errorBody}` : ''}`,
				{ status: response!.status }
			);
		}

		// Special handling for HLS playlists - rewrite URLs
		if (videoType === 'hls') {
			const playlistContent = await response!.text();
			const baseUrl = getBaseUrl(request);
			const rewrittenPlaylist = rewriteHlsPlaylist(
				playlistContent,
				decodedVideoUrl,
				baseUrl,
				referer,
				userAgent,
				cookiesStr
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

		// Extract response headers
		const contentLength = response!.headers.get('content-length');
		const contentType = response!.headers.get('content-type') || 'video/mp4';
		const contentDisposition = response!.headers.get('content-disposition');
		const acceptRanges = response!.headers.get('accept-ranges') || 'bytes';

		// Determine filename
		const filename = getFilename(decodedVideoUrl, contentDisposition || undefined);

		// Prepare response headers
		const responseHeaders: Record<string, string> = {
			'Content-Type': contentType,
			'Accept-Ranges': acceptRanges,
			'Access-Control-Allow-Origin': '*',
			'Access-Control-Allow-Methods': 'GET, HEAD, OPTIONS',
			'Access-Control-Allow-Headers': 'Range, Content-Type, Authorization',
			'Access-Control-Expose-Headers':
				'Content-Length, Content-Range, Content-Type, Content-Disposition'
		};

		// Set cache control based on content type
		if (videoType === 'hls_fragment') {
			// HLS fragments can be cached longer
			responseHeaders['Cache-Control'] = 'public, max-age=3600';
		} else {
			responseHeaders['Cache-Control'] = 'public, max-age=3600';
		}

		// Set content disposition based on request type
		if (forceDownload) {
			responseHeaders['Content-Disposition'] = `attachment; filename="${filename}"`;
		} else {
			// For streaming, use inline disposition
			responseHeaders['Content-Disposition'] = `inline; filename="${filename}"`;
		}

		if (contentLength) {
			responseHeaders['Content-Length'] = contentLength;
		}

		// Handle partial content (range requests)
		if (range && response!.status === 206) {
			const contentRange = response!.headers.get('content-range');
			if (contentRange) {
				responseHeaders['Content-Range'] = contentRange;
			}

			logger.info(`Streaming partial content: ${contentRange}`);
			return new Response(response!.body, {
				status: 206,
				headers: responseHeaders
			});
		}

		// Stream full content
		const contentLengthMB = contentLength
			? (parseInt(contentLength) / 1024 / 1024).toFixed(1) + ' MB'
			: 'Unknown size';

		const action = forceDownload ? 'download' : 'stream';
		logger.success(`${action} ${filename} (${contentLengthMB})`);

		return new Response(response!.body, {
			status: 200,
			headers: responseHeaders
		});
	} catch (error: any) {
		logger.error('Error processing video request:', error.message);
		logger.error('Video URL:', decodedVideoUrl);
		logger.error('Referer:', referer);

		return new Response(`Error processing video: ${error.message}`, {
			status: 500
		});
	}
};

// Handle OPTIONS requests for CORS
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
