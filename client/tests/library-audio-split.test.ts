import { beforeEach, describe, expect, it } from 'vitest';

import { LibraryStore } from '../src/lib/stores/library.svelte';

import type { AudioSplitDone, IncomingVideo } from '../src/lib/types';

function incomingVideo(): IncomingVideo {
	return {
		metadata: { title: 'Demo', webpage_url: 'https://example.com/v' },
		formats: [
			{
				format_id: '18',
				ext: 'mp4',
				resolution: 720,
				tbr: 1000,
				protocol: 'https',
				sourceVideoUrl: 'https://example.com/v.mp4'
			}
		]
	};
}

function doneSplit(): AudioSplitDone {
	return { state: 'done', exportId: 'abc123', filename: 'demo.mp3' };
}

describe('library store split-audio persistence (online cards)', () => {
	beforeEach(() => {
		localStorage.clear();
	});

	it('rides the finished split on the card (same object the UI reads)', () => {
		const store = new LibraryStore();

		store.addExtractResult(incomingVideo());
		const [video] = store.extractResults;

		store.setAudioSplit(video, doneSplit());

		// The UI re-renders off `extractResults`; the split must live there.
		expect(video.audioSplit?.filename).toBe('demo.mp3');
		expect(video.audioSplit?.exportId).toBe('abc123');
	});

	it('clearing the split removes it from the card', () => {
		const store = new LibraryStore();

		store.addExtractResult(incomingVideo());
		const [video] = store.extractResults;

		store.setAudioSplit(video, doneSplit());
		store.setAudioSplit(video, null);

		expect(video.audioSplit).toBeUndefined();
	});

	it('adds and removes a split without breaking dedupe of the same source', () => {
		const store = new LibraryStore();

		store.addExtractResult(incomingVideo());
		store.setAudioSplit(store.extractResults[0]!, doneSplit());

		expect(store.addExtractResult(incomingVideo())).toBe(false);
		expect(store.extractResults).toHaveLength(1);
		expect(store.extractResults[0]?.audioSplit?.filename).toBe('demo.mp3');
	});
});