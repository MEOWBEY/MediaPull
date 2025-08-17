import { json } from '@sveltejs/kit';
import { SERVER_BASE_URL, CLIENT_BASE_URL } from '$env/static/private';
import { logger } from '$lib/server/logger.js';
import type { RequestHandler } from './$types.js';
export const POST: RequestHandler = async ({ request }) => {
	try {
		const { url } = await request.json();
		if (!url) throw new Error('No Site URL provided');

		const serverUrl = SERVER_BASE_URL || 'http://localhost:8000';
		logger.info(`Extracting videos from: ${url}`);

		// This server runs yt-dlp to extract video info
		const response = await fetch(`${serverUrl}/extract-videos`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ url })
		});

		// Throw error for non-OK responses so they go to catch
		if (!response.ok) {
			const error = await response.json().catch(() => ({}));
			throw new Error(error.detail || `Server error: ${response.status}`);
		}

		const data = await response.json();

		const formats = (data.video?.formats || []).map((format: any) => ({
			id: format.format_id,
			quality: format.format,
			resolution: format.resolution,
			width: format.width,
			height: format.height,
			fileSize: format.filesize || null,
			extension: format.ext,
			protocol: format.protocol,
			originalUrl: format.url || format.manifest_url || '',
			downloadUrl: `${CLIENT_BASE_URL}/api/proxy-video?url=${encodeURIComponent(format.url || '')}&userAgent=${encodeURIComponent(format.http_headers?.['User-Agent'] || '')}`,
			thumbnail: format.thumbnail || '',
			isHLS: format.protocol === 'm3u8_native'
		}));

		logger.success(`Found ${formats.length} video formats`);

		return json({
			success: true,
			video: {
				duration: data.video.duration,
				formats,
				totalFormats: formats.length
			}
		});
	} catch (error) {
		const message = error instanceof Error ? error.message : 'Unknown error';
		logger.error('Extract videos error:', message);

		return json({ success: false, error: message }, { status: 500 });
	}
};
