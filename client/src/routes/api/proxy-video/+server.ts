import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types.js';

export const GET: RequestHandler = async ({ url, fetch, request }) => {
	try {
		// Extract query parameters
		const sourceVideoUrl = url.searchParams.get('url');
		const protocol = url.searchParams.get('protocol') ?? '';
		const userAgent = url.searchParams.get('userAgent') ?? '';
		const referer = url.searchParams.get('referer') ?? '';
		const cookies = url.searchParams.get('cookies') ?? '';

		if (!sourceVideoUrl || !protocol) {
			return json({ error: 'Missing url or protocol' }, { status: 400 });
		}

		// Build request headers for upstream fetch
		const upstreamHeaders: Record<string, string> = {};
		if (userAgent) upstreamHeaders['User-Agent'] = userAgent;
		if (referer) upstreamHeaders['Referer'] = referer;
		if (cookies) upstreamHeaders['Cookie'] = cookies;

		// Pass through Range header for seeking
		const rangeHeader = request.headers.get('range');
		if (rangeHeader) upstreamHeaders['Range'] = rangeHeader;

		const upstreamResponse = await fetch(sourceVideoUrl, { headers: upstreamHeaders });

		if (!upstreamResponse.ok) {
			return json(
				{ error: `Upstream error: ${upstreamResponse.status}` },
				{ status: upstreamResponse.status }
			);
		}

		// Handle HLS playlist rewriting
		if (protocol === 'm3u8_native') {
			const playlist = await upstreamResponse.text();

			const playlistParams = new URLSearchParams();
			playlistParams.set('protocol', 'segment');
			if (userAgent) playlistParams.set('userAgent', userAgent);
			if (referer) playlistParams.set('referer', referer);
			if (cookies) playlistParams.set('cookies', cookies);

			const proxiedVideoUrl = `${url.origin}${url.pathname}`;
			const proxiedPlaylist = proxyHlsPlaylistUrls(
				playlist,
				sourceVideoUrl,
				proxiedVideoUrl,
				playlistParams
			);

			return new Response(proxiedPlaylist, {
				status: 200,
				headers: {
					'Content-Type': 'application/vnd.apple.mpegurl',
					'Access-Control-Allow-Origin': '*',
					'Cache-Control': 'no-cache'
				}
			});
		}

		// Handle HLS segments (protocol=segment) and MP4
		const responseHeaders = new Headers();
		for (const [key, value] of upstreamResponse.headers.entries()) {
			if (
				[
					'content-type',
					'content-length',
					'content-range',
					'accept-ranges',
					'content-disposition'
				].includes(key.toLowerCase())
			) {
				responseHeaders.set(key, value);
			}
		}
		responseHeaders.set('Access-Control-Allow-Origin', '*');
		responseHeaders.set('Accept-Ranges', 'bytes');

		return new Response(upstreamResponse.body, {
			status: upstreamResponse.status,
			headers: responseHeaders
		});
	} catch (error) {
		const message = error instanceof Error ? error.message : 'Unknown error';
		return json({ error: message }, { status: 500 });
	}
};

// rewrite HLS playlist URIs to go through proxy
function proxyHlsPlaylistUrls(
	playlist: string,
	sourceVideoUrl: string,
	proxiedVideoUrl: string,
	params: URLSearchParams
): string {
	const sourceUrl = new URL(sourceVideoUrl);

	return playlist
		.split('\n')
		.map((line) => {
			if (line.startsWith('#') || !line.trim()) return line;

			let absUrl: string;
			try {
				absUrl = new URL(line, sourceUrl).toString();
			} catch {
				return line;
			}

			const newParams = new URLSearchParams(params);
			newParams.set('url', absUrl);

			return `${proxiedVideoUrl}?${newParams.toString()}`;
		})
		.join('\n');
}
