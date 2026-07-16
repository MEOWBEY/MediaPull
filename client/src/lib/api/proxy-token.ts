/**
 * Exchange a source's auth cookies for an opaque, short-lived token.
 *
 * Cookies must never appear in the proxied media URL — those URLs get copied,
 * turned into QR codes, and shared, which would leak the user's logged-in
 * session for the source site. The server (`POST /proxy-token`) stashes the
 * cookies behind a token; the proxy URL then carries only the token (`?ctok=`).
 *
 * `resolveVideoCookieTokens` / `resolveGalleryCookieTokens` walk a freshly
 * extracted result, mint one token per distinct cookie blob, and rewrite the
 * incoming data in place so the raw `Cookie` header is dropped and a
 * `cookieToken` is attached instead — before the (synchronous) transform ever
 * builds a proxy URL.
 */

import { postJson } from '$lib/api/client';
import type { IncomingGallery, IncomingVideo } from '$lib/types';

interface ProxyTokenResponse {
	token: string;
}

/** Mint a token for `cookies`. Returns '' if the exchange fails (playback then
 *  falls back to no cookies, which is no worse than before and never leaks). */
export async function createProxyToken(cookies: string): Promise<string> {
	if (!cookies) {
		return '';
	}

	try {
		const { token } = await postJson<ProxyTokenResponse>('/proxy-token', { cookies });

		return token || '';
	} catch {
		return '';
	}
}

/** Pull the `Cookie` header out of an httpHeaders bag (case-insensitive). */
function pickCookie(headers: Record<string, string> | null | undefined): string {
	if (!headers) {
		return '';
	}

	return headers['Cookie'] || headers['cookie'] || '';
}

/** Strip any `Cookie`/`cookie` entry from an httpHeaders bag in place. */
function stripCookie(headers: Record<string, string> | null | undefined): void {
	if (!headers) {
		return;
	}
	delete headers['Cookie'];
	delete headers['cookie'];
}

/**
 * Mint one token per distinct cookie blob found across a batch of header bags,
 * then rewrite each bag: drop the raw cookie, and hand back a map from bag ->
 * token so the caller can attach it to the matching item. One network round per
 * distinct cookie value (usually zero or one for a whole extraction).
 */
async function mintTokensFor(
	bags: Array<Record<string, string> | null | undefined>
): Promise<Map<Record<string, string>, string>> {
	// Distinct cookie blob -> token, minted once and reused.
	const byCookie = new Map<string, string>();
	const result = new Map<Record<string, string>, string>();

	for (const bag of bags) {
		const cookie = pickCookie(bag);

		if (!cookie || !bag) {
			continue;
		}

		if (!byCookie.has(cookie)) {
			byCookie.set(cookie, await createProxyToken(cookie));
		}

		const token = byCookie.get(cookie) ?? '';

		stripCookie(bag);

		if (token) {
			result.set(bag, token);
		}
	}

	return result;
}

/**
 * Attach one Settings-cookies token to every item, then mint any leftover
 * Cookie headers (rare after server-side strip). Prefer *cookiesText* — that
 * is what the user pasted for this host; extract JSON no longer carries
 * Cookie (session leak fix).
 */
async function applyCookieTokens(
	items: Array<{ httpHeaders?: Record<string, string> | null; cookieToken?: string }>,
	cookiesText?: string | null
): Promise<void> {
	let shared = '';

	if (cookiesText?.trim()) {
		shared = await createProxyToken(cookiesText.trim());
	}

	const tokens = await mintTokensFor(items.map((item) => item.httpHeaders));

	for (const item of items) {
		const fromHeaders = item.httpHeaders ? tokens.get(item.httpHeaders) : undefined;
		const token = fromHeaders || shared;

		if (token) {
			item.cookieToken = token;
		}
		stripCookie(item.httpHeaders);
	}
}

/** Resolve cookie tokens for every format of a freshly extracted video, in
 *  place. After this, no format's httpHeaders carries a raw cookie; formats
 *  whose cookie was tokenized gain a `cookieToken`. */
export async function resolveVideoCookieTokens(
	video: IncomingVideo,
	cookiesText?: string | null
): Promise<void> {
	await applyCookieTokens((video.formats ?? []).filter(Boolean), cookiesText);
}

/** Gallery equivalent of `resolveVideoCookieTokens`. */
export async function resolveGalleryCookieTokens(
	gallery: IncomingGallery,
	cookiesText?: string | null
): Promise<void> {
	await applyCookieTokens((gallery.images ?? []).filter(Boolean), cookiesText);
}
