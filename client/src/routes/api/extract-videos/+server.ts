import { json } from '@sveltejs/kit';
import { SERVER_BASE_URL, CLIENT_BASE_URL } from '$env/static/private';
import { logger } from '$lib/server/logger.js';
import type { RequestHandler } from './$types.js';
import type { VideoFormat, VideoMetadata } from '$lib/stores/app-state.svelte';

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

		const formats = (data.video?.formats || []).map((format: VideoFormat) => ({
			format_id: format.format_id || '',
			resolution: format.resolution || '',
			ext: format.ext || '',
			tbr: format.tbr || '',
			protocol: format.protocol || '',
			originalUrl: format.url || '',
			downloadUrl: `${CLIENT_BASE_URL}/api/proxy-video?url=${encodeURIComponent(format.url || '')}&userAgent=${encodeURIComponent(format.http_headers?.['User-Agent'] || '')}`
		}));

		logger.success(`Found ${formats.length} video formats`);

		const metadata: VideoMetadata = {
			id: data.video?.id ?? null,
			title: data.video?.title ?? null,
			duration: data.video?.duration ?? null,
			width: data.video?.width ?? null,
			height: data.video?.height ?? null,
			thumbnail: data.video?.thumbnail ?? null,
			upload_date: data.video?.upload_date ?? null,
			webpage_url: data.video?.webpage_url ?? null,
			aspect_ratio: data.video?.aspect_ratio ?? null
		};

		return json({
			success: true,
			video: { metadata, formats }
		});
	} catch (error) {
		const message = error instanceof Error ? error.message : 'Unknown error';
		logger.error('Extract videos error:', message);

		return json({ success: false, error: message }, { status: 500 });
	}
};
