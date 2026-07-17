import { describe, expect, it } from 'vitest';

import { segmentsToSrt, segmentsToVttUrl } from '../src/lib/subtitle-utils';

describe('segmentsToSrt', () => {
	it('serializes cues with comma millis and indices', () => {
		const srt = segmentsToSrt([
			{ start: 1, end: 2.5, text: 'Hello' },
			{ start: 3, end: 4, text: 'World' }
		]);

		expect(srt).toContain('1\n');
		expect(srt).toContain('00:00:01,000 --> 00:00:02,500');
		expect(srt).toContain('Hello');
		expect(srt).toContain('2\n');
		expect(srt).toContain('World');
	});
});

describe('segmentsToVttUrl', () => {
	it('returns a blob: URL', () => {
		const url = segmentsToVttUrl([{ start: 0, end: 1, text: 'Hi' }]);

		expect(url.startsWith('blob:')).toBe(true);
		URL.revokeObjectURL(url);
	});
});
