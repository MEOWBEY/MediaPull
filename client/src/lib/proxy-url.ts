/**
 * Build the proxied media URL the player/downloader hits instead of the source.
 *
 * The backend's `/proxy-video` replays the request to the source with the right
 * Referer/Cookie/User-Agent (which a browser can't set on a media element) and
 * rewrites HLS playlists. Building the URL on the client keeps the backend
 * ignorant of its own public URL and makes "skip the proxy" (e.g. on Android)
 * trivial.
 */

import { API_BASE_URL } from '$lib/config';

type Headers = Record<string, string> | null | undefined;

/**
 * Absolute origin the proxied URL must point at. In dev `API_BASE_URL` is empty
 * (requests stay relative and Vite proxies them), but a *relative* `/proxy-video`
 * is useless once it leaves the page — a copied link or a QR code scanned on a
 * phone has no origin to resolve against. So fall back to the current origin to
 * keep copy/QR/share links absolute and resolvable. The player/download (same
 * origin) are unaffected.
 */
function proxyOrigin(): string {
	if (API_BASE_URL) {return API_BASE_URL;}

	return typeof window === 'undefined' ? '' : window.location.origin;
}

function pick(headers: Headers, ...names: string[]): string {
	if (!headers) {return '';}
	for (const name of names) {
		const value = headers[name];

		if (value) {return value;}
	}

	return '';
}

/**
 * `sourceUrl` + upstream headers → `${API_BASE_URL}/proxy-video?...`.
 *
 * Auth cookies are NEVER placed in the URL — they'd leak through copy/QR/share
 * links. Instead the caller passes `cookieToken` (minted via `POST /proxy-token`,
 * see `$lib/api/proxy-token`) and the proxy resolves it server-side.
 */
export function buildProxiedUrl(
	sourceUrl: string | undefined,
	httpHeaders: Headers,
	protocol: string | undefined,
	cookieToken?: string | null
): string {
	if (!sourceUrl) {return '';}

	const params = new URLSearchParams({
		url: sourceUrl,
		protocol: protocol || 'https'
	});

	const referer = pick(httpHeaders, 'Referer', 'referer');

	// User-Agent is deliberately NOT sent: the server proxies with curl_cffi
	// browser impersonation by default, which sets its own UA to match the TLS
	// fingerprint and ignores this param; in the rare no-impersonation fallback
	// it uses its own default UA. Omitting it also keeps the URL (and its QR
	// code) shorter.
	if (referer) {params.set('referer', referer);}
	if (cookieToken) {params.set('ctok', cookieToken);}

	return `${proxyOrigin()}/proxy-video?${params.toString()}`;
}
