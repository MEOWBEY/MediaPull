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
			signal: AbortSignal.timeout(500000) // 60 seconds timeout
		});

		if (!response.ok) {
			const errorData = await response.json().catch(() => ({}));
			console.error('Python server error:', errorData);
			throw new Error(errorData.error || `Python server error: ${response.status}`);
		}

		const data = await response.json();
		console.log(`Extracted ${data.videos?.length || 0} videos`);
		let proxyUrl = '';
		// Process videos and create proxy URLs with streaming support
		const videosWithProxy =
			data.videos?.map((video, index) => {
				console.log(`Processing video ${index + 1}:`, {
					title: video.title,
					quality: video.quality,
					videoType: video.videoType,
					isDirectStream: video.isDirectStream,
					hasStreamUrl: !!video.streamUrl
				});

				// Create multiple download options
				const downloadOptions = [];

				// Option 1: Direct streaming from Python server (preferred for HLS/fragmented videos)
				if (video.streamUrl) {
					downloadOptions.push({
						type: 'python_stream',
						url: `${pythonServerUrl}${video.streamUrl}`,
						label: 'Stream (Python Server)',
						recommended: video.videoType === 'hls' || video.videoType === 'hls_fragment'
					});
				}

				// Option 2: Proxy through Node.js (for direct MP4 URLs)
				if (video.downloadUrl) {
					const encodedUrl = encodeURIComponent(video.downloadUrl);
					const encodedReferer = encodeURIComponent(video.referer || '');
					const encodedUserAgent = encodeURIComponent(video.userAgent || '');

					let cookiesParam = '';
					if (video.cookies && video.cookies.length > 0) {
						try {
							const cookiesStr = JSON.stringify(video.cookies);
							cookiesParam = `&cookies=${encodeURIComponent(cookiesStr)}`;
						} catch (e) {
							console.warn('Failed to serialize cookies for video:', video.title);
						}
					}

					proxyUrl = `${env.PUBLIC_BASE_URL}/api/download-video?url=${encodedUrl}&referer=${encodedReferer}&userAgent=${encodedUserAgent}${cookiesParam}`;

					downloadOptions.push({
						type: 'node_proxy',
						url: proxyUrl,
						label: 'Download (Node Proxy)',
						recommended: video.videoType === 'direct'
					});
				}
				return {
					...video,
					originalUrl: video.downloadUrl,
					downloadUrl: proxyUrl,
					downloadOptions,
				};
			}) || [];




		return json({
			...data,
			videos: videosWithProxy,
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
