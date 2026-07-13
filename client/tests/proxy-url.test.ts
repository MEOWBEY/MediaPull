import { describe, expect, it } from 'vitest';

import { buildProxiedUrl } from '$lib/proxy-url';

describe('buildProxiedUrl', () => {
	it('returns empty string when source missing', () => {
		expect(buildProxiedUrl(undefined, null, 'https')).toBe('');
	});

	it('puts url and protocol in the query', () => {
		const out = buildProxiedUrl('https://cdn.example.com/v.mp4', null, 'm3u8_native');

		expect(out).toContain(`url=${encodeURIComponent('https://cdn.example.com/v.mp4')}`);
		expect(out).toContain('protocol=m3u8_native');
	});

	it('never puts cookies in the URL, even when headers carry a Cookie', () => {
		const out = buildProxiedUrl(
			'https://cdn.example.com/v.mp4',
			{ Cookie: 'sid=secret; auth=1' },
			'https'
		);

		expect(out).not.toContain('cookies=');
		expect(out).not.toContain('sid=secret');
		expect(out).not.toContain('auth=1');
	});

	it('carries an opaque cookie token as ctok', () => {
		const out = buildProxiedUrl('https://cdn.example.com/v.mp4', null, 'https', 'tok123');

		expect(out).toContain('ctok=tok123');
	});

	it('still forwards non-secret referer/userAgent', () => {
		const out = buildProxiedUrl(
			'https://cdn.example.com/v.mp4',
			{ Referer: 'https://site.example/', 'User-Agent': 'UA/1' },
			'https'
		);

		expect(out).toContain(`referer=${encodeURIComponent('https://site.example/')}`);
		expect(out).toContain('userAgent=UA%2F1');
	});
});
