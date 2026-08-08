import 'fake-indexeddb/auto';
import { beforeEach, describe, expect, it } from 'vitest';

import type { SubtitleTrackResult } from '$lib/types';

import { localFiles } from '../src/lib/stores/local-library.svelte';

function makeFile(): File {
	return new File(['video content'], 'clip.mp4', { type: 'video/mp4' });
}

function track(): SubtitleTrackResult {
	return {
		language: 'en',
		segments: [{ start: 0, end: 1.5, text: 'Hello' }],
		vttUrl: 'blob:mediapull-test-vtt',
		srtUrl: 'blob:mediapull-test-srt'
	};
}

beforeEach(async () => {
	// jsdom/fake-indexeddb don't round-trip File as a Blob instance, so the
	// real createObjectURL would reject — stub it (real browsers preserve Files).
	URL.createObjectURL = (() => `blob:stub-${Math.random().toString(36).slice(2)}`) as unknown as (
		obj: Blob | MediaSource
	) => string;

	// Reset in-memory state AND wipe the fixed-name DB so restore() sees a
	// clean store each test.
	localFiles.entries = [];
	const db = await new Promise<IDBDatabase>((resolve, reject) => {
		const req = indexedDB.open('mediapull', 2);

		req.onupgradeneeded = () => {
			if (!req.result.objectStoreNames.contains('local-files')) {
				req.result.createObjectStore('local-files', { keyPath: 'id' });
			}
		};
		req.onsuccess = () => resolve(req.result);
		req.onerror = () => reject(req.error);
	});
	const all = await new Promise<IDBValidKey[]>((resolve, reject) => {
		const req = db
			.transaction('local-files', 'readonly')
			.objectStore('local-files')
			.getAllKeys();

		req.onsuccess = () => resolve(req.result);
		req.onerror = () => reject(req.error);
	});

	for (const key of all) {
		const store = db.transaction('local-files', 'readwrite').objectStore('local-files');

		await new Promise<void>((resolve, reject) => {
			const req = store.delete(key);

			req.onsuccess = () => resolve();
			req.onerror = () => reject(req.error);
		});
	}
	db.close();
});

describe('local-library store (emulates a page session + refresh)', () => {
	it('adds an entry with a blob URL and latest-first order', async () => {
		await localFiles.add(makeFile());

		expect(localFiles.entries).toHaveLength(1);
		expect(localFiles.entries[0]!.blobUrl.startsWith('blob:')).toBe(true);
		expect(localFiles.byId(localFiles.entries[0]!.id)).toBeDefined();
	});

	it('keeps the resolved subtitle on the record', async () => {
		await localFiles.add(makeFile());
		const { id } = localFiles.entries[0]!;

		await localFiles.setSubtitle(id, track());

		expect(localFiles.byId(id)?.subtitle?.segments).toHaveLength(1);
	});

	it('restores entries with their subtitle after a "refresh" (IDB round-trip)', async () => {
		await localFiles.add(makeFile());
		const { id } = localFiles.entries[0]!;

		await localFiles.setSubtitle(id, track());

		// Refresh: in-memory state is gone, only IndexedDB remains.
		localFiles.entries = [];
		await localFiles.restore();

		const [restored] = localFiles.entries;

		expect(restored?.id).toBe(id);
		expect(restored?.subtitle?.segments).toHaveLength(1);
		expect(restored?.subtitle?.language).toBe('en');
		expect(restored?.blobUrl.startsWith('blob:')).toBe(true);
	});

	it('restores a finished audio split next to the file', async () => {
		await localFiles.add(makeFile());
		const { id } = localFiles.entries[0]!;

		await localFiles.setAudioSplit(id, { state: 'done', exportId: 'xyz', filename: 'a.mp3' });
		localFiles.entries = [];
		await localFiles.restore();

		const [restored] = localFiles.entries;

		expect(restored?.audioSplit?.filename).toBe('a.mp3');
	});

	it('drops the entry (and its record) on remove', async () => {
		await localFiles.add(makeFile());
		const { id } = localFiles.entries[0]!;

		localFiles.remove(id);
		await localFiles.restore();

		expect(localFiles.entries).toHaveLength(0);
	});
});