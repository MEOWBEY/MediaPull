import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { IncomingVideo } from '$lib/types';

// Mock the low-level API so no real network happens. postJson returns a token.
const postJson = vi.fn();

vi.mock('$lib/api/client', () => ({ postJson: (...a: unknown[]) => postJson(...a) }));

const { resolveVideoCookieTokens } = await import('$lib/api/proxy-token');

describe('resolveVideoCookieTokens', () => {
	beforeEach(() => {
		postJson.mockReset();
	});

	it('mints one token per distinct cookie and strips the raw Cookie header', async () => {
		postJson.mockResolvedValue({ token: 'TOK' });

		const video: IncomingVideo = {
			formats: [
				{ sourceVideoUrl: 'https://a/1.mp4', httpHeaders: { Cookie: 'sid=1', Referer: 'r' } },
				{ sourceVideoUrl: 'https://a/2.mp4', httpHeaders: { Cookie: 'sid=1' } }
			]
		};

		await resolveVideoCookieTokens(video);

		// One network call for the single distinct cookie blob.
		expect(postJson).toHaveBeenCalledTimes(1);
		expect(postJson).toHaveBeenCalledWith('/proxy-token', { cookies: 'sid=1' });

		for (const f of video.formats ?? []) {
			expect(f.cookieToken).toBe('TOK');
			expect(f.httpHeaders?.Cookie).toBeUndefined();
		}
		// Non-cookie headers survive.
		expect(video.formats?.[0].httpHeaders?.Referer).toBe('r');
	});

	it('does nothing (no token, no call) when there are no cookies', async () => {
		const video: IncomingVideo = {
			formats: [{ sourceVideoUrl: 'https://a/1.mp4', httpHeaders: { Referer: 'r' } }]
		};

		await resolveVideoCookieTokens(video);

		expect(postJson).not.toHaveBeenCalled();
		expect(video.formats?.[0].cookieToken).toBeUndefined();
	});

	it('leaves no raw cookie even if the token exchange fails', async () => {
		postJson.mockRejectedValue(new Error('network'));

		const video: IncomingVideo = {
			formats: [{ sourceVideoUrl: 'https://a/1.mp4', httpHeaders: { Cookie: 'sid=1' } }]
		};

		await resolveVideoCookieTokens(video);

		expect(video.formats?.[0].cookieToken).toBeUndefined();
		expect(video.formats?.[0].httpHeaders?.Cookie).toBeUndefined();
	});
});
