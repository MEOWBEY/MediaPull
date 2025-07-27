import { json } from '@sveltejs/kit';
import { puppeteerService } from '$lib/server/puppeteer.js';
import { logger } from '$lib/server/logger';
import type { RequestHandler } from './$types.js';

export const POST: RequestHandler = async ({ request }) => {
	const startTime = Date.now();

	try {
		const { userVideoUrl, method } = await request.json();

		if (!userVideoUrl) {
			logger.error('No video URL provided');
			return json({ error: 'No video URL provided' }, { status: 400 });
		}

		// Validate URL format
		try {
			new URL(userVideoUrl);
		} catch {
			logger.error('Invalid URL format provided');
			return json({ error: 'Invalid URL format' }, { status: 400 });
		}

		logger.info(`Processing video URL: ${userVideoUrl}`);
		logger.info(`Processing method: ${method || 'puppeteer'}`);

		// Choose processing method
		const processingMethod = method || 'auto';
		let result;

		if (processingMethod === 'puppeteer' || processingMethod === 'auto') {
			try {
				logger.info('Attempting Puppeteer processing...');
				result = await processWithPuppeteer(userVideoUrl);

				// If puppeteer succeeds, return the result
				if (result.success) {
					const processingTime = Date.now() - startTime;
					logger.success(`Video processed successfully with Puppeteer in ${processingTime}ms`);
					return json({
						...result,
						processingTime,
						method: 'puppeteer'
					});
				}
			} catch (error: any) {
				logger.warn(`Puppeteer processing failed: ${error.message}`);
				// If we get here, both methods failed or only puppeteer was requested
				throw error;
			}
		}

		if (!result || !result.success) {
			throw new Error('All processing methods failed');
		}

		const processingTime = Date.now() - startTime;
		logger.success(`Video processed successfully in ${processingTime}ms`);

		return json({
			...result,
			processingTime,
			method: processingMethod
		});
	} catch (error: any) {
		const processingTime = Date.now() - startTime;
		logger.error(`Video processing failed after ${processingTime}ms:`, error.message);

		return json(
			{
				success: false,
				error: 'Failed to process the video',
				details: error.message,
				timestamp: new Date().toISOString(),
				processingTime,
				availableMethods: ['puppeteer', 'python', 'auto']
			},
			{ status: 500 }
		);
	}
};

// Puppeteer processing function
async function processWithPuppeteer(userVideoUrl: string) {
	const result = await puppeteerService.getProcessedVideoInfo(userVideoUrl);

	// Create download URL with improved proxy
	const downloadUrl = `/api/download-video?url=${encodeURIComponent(
		result.videoSrc
	)}&referer=${encodeURIComponent('https://online-video-cutter.com/')}&cookies=${encodeURIComponent(
		JSON.stringify(result.cookies)
	)}&userAgent=${encodeURIComponent(result.userAgent)}`;

	return {
		success: true,
		videoSrc: result.videoSrc,
		downloadUrl,
		cookies: result.cookies,
		userAgent: result.userAgent,
		filename: result.filename || 'unknown',
		size: result.size || 'unknown',
		method: 'puppeteer',
		videoType: 'direct' // Puppeteer typically gets direct URLs
	};
}