import { json } from '@sveltejs/kit';
import { SERVER_BASE_URL, CLIENT_BASE_URL } from '$env/static/private';
import { logger } from '$lib/server/logger.js';
import type { RequestHandler } from './$types.js';

export const POST: RequestHandler = async ({ request }) => {
	try {
		const { url } = await request.json();
		if (!url) throw new Error('No Site URL provided');

		logger.info(`Extracting videos from: ${url}`);

		const response = await fetch(`${SERVER_BASE_URL}/extract-videos`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ url })
		});

		if (!response.ok) {
			const error = await response.json().catch(() => ({}));
			throw new Error(error.detail || `Server error: ${response.status}`);
		}

		const data = await response.json();

		const formats = (data.video?.formats ?? []).map((format) => ({
			format_id: format?.format_id ?? 'unknown',
			resolution: format?.resolution ?? 'N/A',
			ext: format?.ext ?? '',
			tbr: format?.tbr ?? 0,
			protocol: format?.protocol ?? '',
			sourceVideoUrl: format?.url ?? '',
			proxiedVideoUrl: `${CLIENT_BASE_URL}/api/proxy-video?${new URLSearchParams({
				url: format?.url ?? '',
				protocol: format?.protocol ?? 'http',
				userAgent: format.http_headers?.['User-Agent'] ?? ''
			}).toString()}`
		}));

		const metadata = {
			id: data.video?.id ?? null,
			title: data.video?.title ?? 'Untitled',
			duration: data.video?.duration ?? 0,
			width: data.video?.width ?? 0,
			height: data.video?.height ?? 0,
			thumbnail: data.video?.thumbnail ?? '',
			upload_date: data.video?.upload_date ?? '',
			webpage_url: data.video?.webpage_url ?? '',
			aspect_ratio: data.video?.aspect_ratio ?? 0
		};

		logger.success(`Found ${formats.length} video formats`);

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
