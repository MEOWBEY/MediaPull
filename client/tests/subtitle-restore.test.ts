import { describe, expect, it } from 'vitest';

import { SubtitleResolver } from '../src/lib/subtitle-resolver.svelte';

import type { SubtitleTrackResult } from '../src/lib/types';

/** A track exactly as `local-files.ts` would have persisted it: segments are
 * durable, but the vtt/srt URLs are whatever the server generated at the time
 * (they die with the transcribe job's TTL -- the whole point of rebuilding). */
function persistedTrack(): SubtitleTrackResult {
	return {
		language: 'en',
		segments: [
			{ start: 0, end: 1.5, text: 'Hello' },
			{ start: 2, end: 3, text: 'World' }
		],
		vttUrl: 'http://server/vtt',
		srtUrl: 'http://server/srt'
	};
}

describe('SubtitleResolver.restore (page-refresh signal)', () => {
	it('re-exposes the track from persisted segments', () => {
		const resolver = new SubtitleResolver();

		resolver.restore(persistedTrack());

		expect(resolver.track?.segments).toHaveLength(2);
		expect(resolver.track?.language).toBe('en');
	});

	it("rebuilds blob URLs so playback/download survive the server job's TTL", () => {
		const resolver = new SubtitleResolver();

		resolver.restore(persistedTrack());

		const {track} = resolver;

		expect(track?.vttUrl?.startsWith('blob:')).toBe(true);
		expect(track?.srtUrl?.startsWith('blob:')).toBe(true);
	});

	it('reports the track as present (hasTrack) after restore', () => {
		const resolver = new SubtitleResolver();

		resolver.restore(persistedTrack());

		expect(Boolean(resolver.track)).toBe(true);
	});
});