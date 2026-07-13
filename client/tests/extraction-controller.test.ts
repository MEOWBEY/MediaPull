import { describe, expect, it } from 'vitest';

import { ExtractionController } from '$lib/extraction.svelte';

describe('ExtractionController.start', () => {
	it('aborts the previous in-flight controller when re-entered', () => {
		const c = new ExtractionController();

		// `start` is private; reach in for a white-box lifecycle check.
		(c as unknown as { start(): void }).start();
		const first = (c as unknown as { controller: AbortController }).controller;

		expect(first.signal.aborted).toBe(false);

		(c as unknown as { start(): void }).start();

		expect(first.signal.aborted).toBe(true);
		expect((c as unknown as { controller: AbortController }).controller).not.toBe(first);

		// Clean up the timer the second start() spun up.
		(c as unknown as { stop(): void }).stop();
	});
});
