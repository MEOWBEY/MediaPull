import { json } from '@sveltejs/kit';
import { PYTHON_VIDEO_SERVER_URL } from '$env/static/private';
import { env } from '$env/dynamic/public';

/** @type {import('./$types').RequestHandler} */
export async function POST({ request }) {
	try {
		const { url } = await request.json();

		if (!url) {
			return json(
				{
					success: false,
					error: 'URL is required'
				},
				{ status: 400 }
			);
		}

		// Validate URL format
		try {
			new URL(url);
		} catch {
			return json(
				{
					success: false,
					error: 'Invalid URL format'
				},
				{ status: 400 }
			);
		}

		// Forward request to Python server
		const pythonServerUrl = PYTHON_VIDEO_SERVER_URL || 'http://localhost:5000';

		console.log(`Forwarding request to Python server: ${pythonServerUrl}`);
		console.log(`Extracting videos from: ${url}`);

		const response = await fetch(`${pythonServerUrl}/extract-videos`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json'
			},
			body: JSON.stringify({ url }),
			signal: AbortSignal.timeout(500000) // 500 seconds timeout
		});

		if (!response.ok) {
			const errorData = await response.json().catch(() => ({}));
			console.error('Python server error:', errorData);
			throw new Error(errorData.error || `Python server error: ${response.status}`);
		}

		const data = await response.json();

		if (!data.success || !data.video || !data.video.formats) {
			throw new Error('Invalid response format from Python server');
		}

		console.log(`Found ${data.video.formats.length} video formats`);

		// Process video formats and create proxy URLs
		const processedFormats = data.video.formats.map((format, index) => {
			console.log(`Processing format ${index + 1}:`, {
				format_id: format.format_id,
				resolution: format.resolution,
				quality: format.format,
				protocol: format.protocol
			});

			// Create proxy URL for the video
			const videoUrl = format.url || format.manifest_url;
			const encodedUrl = encodeURIComponent(videoUrl);

			// Extract useful headers
			const userAgent = format.http_headers?.['User-Agent'] || '';
			const encodedUserAgent = encodeURIComponent(userAgent);

			// Create proxy download URL
			const proxyUrl = `${env.PUBLIC_BASE_URL}/api/download-video?url=${encodedUrl}&userAgent=${encodedUserAgent}`;

			return {
				id: format.format_id,
				quality: format.format,
				thumbnail: format.thumbnail || '',
				resolution: format.resolution,
				width: format.width,
				height: format.height,
				fileSize: format.filesize || null,
				extension: format.ext,
				protocol: format.protocol,
				originalUrl: videoUrl,
				downloadUrl: proxyUrl,
				isHLS: format.protocol === 'm3u8_native'
			};
		});

		return json({
			success: true,
			video: {
				duration: data.video.duration,
				formats: processedFormats,
				totalFormats: processedFormats.length
			}
		});
	} catch (error) {
		console.error('Error communicating with Python server:', error);

		if (error.name === 'AbortError') {
			return json(
				{
					success: false,
					error: 'Request timeout - video extraction took too long'
				},
				{ status: 408 }
			);
		}

		if (error.message.includes('fetch') || error.code === 'ECONNREFUSED') {
			return json(
				{
					success: false,
					error:
						'Cannot connect to video processing server. Make sure Python server is running on port 5000.',
					details: 'Start the Python server with: python app.py'
				},
				{ status: 503 }
			);
		}

		return json(
			{
				success: false,
				error: error.message || 'Internal server error'
			},
			{ status: 500 }
		);
	}
}
