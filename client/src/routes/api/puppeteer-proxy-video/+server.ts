import { json } from '@sveltejs/kit';
import { puppeteerService } from '$lib/server/puppeteer.js';
import { logger } from '$lib/server/logger.js';
import type { RequestHandler } from './$types.js';

export const POST: RequestHandler = async ({ request }) => {
	try {
		// Parse request body
		const { userVideoUrl, quality, format } = await request.json();

		// Validate input
		if (!userVideoUrl) {
			throw new Error('No video URL provided');
		}

		logger.info(`PuppeteerProxyingUrl video: ${userVideoUrl}`);

		// Use Puppeteer to get video info
		// This launches a browser, navigates to the page, and extracts video data
		const result = await puppeteerService.puppeteerProxiedUrl(userVideoUrl);

		// Create proxy URL for downloading
		// This proxy URL will handle CORS and add proper headers
		const params = new URLSearchParams({
			url: result.videoSrc,
			referer: 'https://online-video-cutter.com/',
			cookies: JSON.stringify(result.cookies),
			userAgent: result.userAgent
		});
		const downloadUrl = `/api/proxy-video?${params.toString()}`;

		// Return successful response with video data
		return json({
			success: true,
			video: {
				// Basic info
				id: `puppeteerProxiedUrl${Math.floor(1000 + Math.random() * 9000)}`,
				originalUrl: userVideoUrl,
				filename: result.filename || 'video.mp4',

				// URLs for streaming and downloading
				downloadUrl, // Proxy URL that handles CORS
				videoSrc: result.videoSrc, // Direct video URL

				// Video properties
				quality: quality || 'Unknown',
				format: format || 'mp4',
				fileSize: result.size || undefined,

				// Optional metadata (if available)
				duration: undefined,
				resolution: undefined,
				fps: undefined,
				bitrate: undefined,
				videoCodec: undefined,
				audioCodec: undefined,
				thumbnail: undefined
			}
		});
	} catch (error) {
		const errorMessage = error instanceof Error ? error.message : 'Unknown error';

		logger.error(`PuppeteerProxyingUrl failed: ${errorMessage}`);

		// Return error response with details
		return json(
			{
				success: false,
				error: 'Failed to puppeteerProxyUrl the video',
				details: errorMessage
			},
			{ status: 500 }
		);
	}
};
