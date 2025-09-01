import { json } from '@sveltejs/kit';
import { puppeteerService } from '$lib/server/puppeteer.js';
import { logger } from '$lib/server/logger.js';
import type { RequestHandler } from './$types.js';
import { CLIENT_BASE_URL } from '$env/static/private';

export const POST: RequestHandler = async ({ request }) => {
	try {
		const { url } = await request.json();
		if (!url) throw new Error('No video URL provided');

		logger.info(`Processing OVC proxy video: ${url}`);

		const response = await puppeteerService.processOvcProxyVideo(url);

		logger.success(`OVC proxy video processed successfully`);

		return json({
			success: true,
			video: {
				id: `ovcProxyVideo${Date.now()}`,
				sourceVideoUrl: url,
				proxiedVideoUrl: `${CLIENT_BASE_URL}/api/proxy-video?${new URLSearchParams({
					url: response?.ovcVideoUrl,
					protocol: 'https',
					referer: response.requestHeaders.referer,
					cookies: JSON.stringify(response.cookies),
					userAgent: response.userAgent
				}).toString()}`,
				ovcVideoUrl: response?.ovcVideoUrl
			}
		});
	} catch (error) {
		const message = error instanceof Error ? error.message : 'Unknown error';
		logger.error(`OVC proxy video error: ${message}`);

		return json(
			{
				success: false,
				error: 'Failed to process OVC proxy video',
				details: message
			},
			{ status: 500 }
		);
	}
};
