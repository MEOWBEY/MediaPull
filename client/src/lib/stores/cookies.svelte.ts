/**
 * Per-site authentication cookies, supplied by the user (Settings → Cookies).
 *
 * Cookies unlock age-restricted / private / login-gated content (YouTube,
 * Instagram, …) and reduce "sign in to confirm you're not a bot" on the server.
 * They are SENSITIVE: kept only in this browser's localStorage (never persisted
 * server-side) and sent per-request only for the URL's matching domain.
 *
 * Mirrors the `PreferencesStore` shape: a `$state` map + load/persist.
 */

import { browser } from '$app/environment';

const STORAGE_KEY = 'cookies';

/** domain (registrable host, e.g. "youtube.com") -> Netscape cookies.txt text. */
export type CookieMap = Record<string, string>;

/** Normalize user input to a bare host: strip scheme/path and a leading www. */
export function normalizeDomain(raw: string): string {
	let d = (raw ?? '').trim().toLowerCase();

	d = d.replace(/^[a-z]+:\/\//, '').replace(/\/.*$/, '').replace(/:\d+$/, '');
	if (d.startsWith('www.')) {d = d.slice(4);}

	return d;
}

export class CookieStore {
	current = $state<CookieMap>({});

	constructor() {
		if (browser) {this.load();}
	}

	entries(): [string, string][] {
		return Object.entries(this.current);
	}

	get(domain: string): string {
		return this.current[normalizeDomain(domain)] ?? '';
	}

	has(domain: string): boolean {
		return Boolean(this.current[normalizeDomain(domain)]?.trim());
	}

	set(domain: string, text: string): void {
		const key = normalizeDomain(domain);

		if (!key) {return;}

		const value = (text ?? '').trim();

		if (value) {this.current[key] = value;}
		else {delete this.current[key];}

		this.persist();
	}

	clear(domain: string): void {
		delete this.current[normalizeDomain(domain)];
		this.persist();
	}

	clearAll(): void {
		this.current = {};
		if (browser) {localStorage.removeItem(STORAGE_KEY);}
	}

	/** Cookie text whose domain best (longest-suffix) matches the URL's host. */
	matchFor(url: string): string | null {
		let host: string;

		try {
			// Local parse for hostname only — not stored, not reactive.
			// eslint-disable-next-line svelte/prefer-svelte-reactivity
			host = new URL(url).hostname.toLowerCase();
		} catch {
			return null;
		}

		let best: string | null = null;
		let bestLen = -1;

		for (const [domain, text] of Object.entries(this.current)) {
			const d = domain.toLowerCase();

			if ((host === d || host.endsWith(`.${d}`)) && d.length > bestLen && text.trim()) {
				best = text;
				bestLen = d.length;
			}
		}

		return best;
	}

	private load(): void {
		try {
			const raw = localStorage.getItem(STORAGE_KEY);

			if (raw) {
				const parsed = JSON.parse(raw);

				if (parsed && typeof parsed === 'object') {Object.assign(this.current, parsed);}
			}
		} catch (error) {
			console.warn('Failed to load cookies:', error);
		}
	}

	private persist(): void {
		if (!browser) {return;}

		try {
			localStorage.setItem(STORAGE_KEY, JSON.stringify(this.current));
		} catch (error) {
			console.warn('Failed to save cookies:', error);
		}
	}
}
