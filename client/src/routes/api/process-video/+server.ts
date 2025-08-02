import { json } from '@sveltejs/kit';
import { puppeteerService } from '$lib/server/puppeteer.js';
import { logger } from '$lib/server/logger';
import type { RequestHandler } from './$types.js';

export const POST: RequestHandler = async ({ request }) => {
	const startTime = Date.now();

	try {
		const { userVideoUrl, method, quality, format } = await request.json();

		if (!userVideoUrl) {
			logger.error('No video URL provided');
			return json(
				{
					success: false,
					error: 'No video URL provided'
				},
				{ status: 400 }
			);
		}

		// Validate URL format
		try {
			new URL(userVideoUrl);
		} catch {
			logger.error('Invalid URL format provided');
			return json(
				{
					success: false,
					error: 'Invalid URL format'
				},
				{ status: 400 }
			);
		}

		logger.info(`Processing video URL: ${userVideoUrl}`);
		logger.info(`Processing method: ${method || 'puppeteer'}`);
		if (quality) logger.info(`Requested quality: ${quality}`);
		if (format) logger.info(`Requested format: ${format}`);

		// Choose processing method
		const processingMethod = method || 'auto';
		let result;

		if (processingMethod === 'puppeteer' || processingMethod === 'auto') {
			try {
				logger.info('Attempting Puppeteer processing...');
				result = await processWithPuppeteer(userVideoUrl, { quality, format });

				// If puppeteer succeeds, return the result
				if (result.success) {
					const processingTime = Date.now() - startTime;
					logger.success(`Video processed successfully with Puppeteer in ${processingTime}ms`);

					return json({
						success: true,
						video: {
							id: `processed_${Date.now()}`,
							originalUrl: userVideoUrl,
							filename: result.filename || 'video.mp4',
							downloadUrl: result.downloadUrl,
							videoSrc: result.videoSrc,
							processedAt: new Date().toISOString(),
							quality: result.quality || quality || 'Unknown',
							format: result.format || format || 'mp4',
							fileSize: result.fileSize,
							duration: result.duration,
							resolution: result.resolution,
							fps: result.fps,
							bitrate: result.bitrate,
							videoCodec: result.videoCodec,
							audioCodec: result.audioCodec,
							thumbnail: result.thumbnail,
							processingTime,
							method: 'puppeteer'
						}
					});
				}
			} catch (error: any) {
				logger.warn(`Puppeteer processing failed: ${error.message}`);
				throw error;
			}
		}

		if (!result || !result.success) {
			throw new Error('All processing methods failed');
		}
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
				availableMethods: ['puppeteer', 'auto']
			},
			{ status: 500 }
		);
	}
};

// Enhanced Puppeteer processing function
async function processWithPuppeteer(
	userVideoUrl: string,
	options: { quality?: string; format?: string } = {}
) {
	const result = await puppeteerService.getProcessedVideoInfo(userVideoUrl);

	// Create download URL with improved proxy
	const downloadUrl = `/api/download-video?url=${encodeURIComponent(
		result.videoSrc
	)}&referer=${encodeURIComponent('https://online-video-cutter.com/')}&cookies=${encodeURIComponent(
		JSON.stringify(result.cookies)
	)}&userAgent=${encodeURIComponent(result.userAgent)}`;

	// Extract additional metadata if available
	const metadata = result.metadata || {};

	return {
		success: true,
		videoSrc: result.videoSrc,
		downloadUrl,
		filename: result.filename || 'video.mp4',
		quality: options.quality || metadata.quality || 'Unknown',
		format: options.format || metadata.format || 'mp4',
		fileSize: metadata.fileSize,
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
		videoType: 'direct'
	};
}
