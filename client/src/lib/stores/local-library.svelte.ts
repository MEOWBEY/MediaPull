/**
 * Local-file library — the store every local-file UI reads and mutates.
 *
 * Follows the project's store pattern: one file per store, persistence kept
 * inside the store itself (like `preferences`/`library`/`cookies` keep their
 * own load/persist). One difference is forced by the data: those stores hold
 * plain JSON (localStorage fits), whereas local files are binary blobs, and
 * IndexedDB is the part of the platform that can structured-clone a File
 * across a refresh — so the private persistence here is IndexedDB.
 *
 * Blob URLs die with the page; entries are rebuilt from the DB on boot
 * (`restore()`) with their resolved subtitle and finished audio split riding
 * along on the same record. Best-effort: quota/open failures are swallowed —
 * the file still works for the current session, it just won't return after a
 * refresh.
 */

import { toast } from 'svelte-sonner';

import { i18n } from '$lib/i18n/index.svelte';
import type { AudioSplitDone, SubtitleTrackResult } from '$lib/types';

export type { AudioSplitDone } from '$lib/types';

const { t } = i18n;

/** Wire record shape stored in IndexedDB (keyed by `id`). */
type PersistedLocalRecord = {
	id: string;
	file: File;
	addedAt?: number;
	subtitle?: SubtitleTrackResult | null;
	audioSplit?: AudioSplitDone | null;
};

/** One open local file, keyed by `id`. Blob URLs die with the page — after a
 *  refresh the entry is rebuilt from IndexedDB (`restore()`). */
export interface LocalFileEntry {
	file: File;
	blobUrl: string;
	id: string;
	addedAt: number;
	/** Resolved subtitle for this file (persisted segments; blob URLs are
	 *  rebuilt by `SubtitleResolver.restore` on mount). */
	subtitle?: SubtitleTrackResult | null;
	/** Finished audio split (the server holds the mp3 for SPLIT_AUDIO_TTL). */
	audioSplit?: AudioSplitDone | null;
}

const DB_NAME = 'mediapull';
const DB_VERSION = 2;
const STORE = 'local-files';

function openDb(): Promise<IDBDatabase> {
	let dbPromise: Promise<IDBDatabase> | null = null;

	return (dbPromise ??= new Promise<IDBDatabase>((resolve, reject) => {
		const req = indexedDB.open(DB_NAME, DB_VERSION);

		req.onupgradeneeded = () => {
			if (!req.result.objectStoreNames.contains(STORE)) {
				req.result.createObjectStore(STORE, { keyPath: 'id' });
			}
		};
		req.onsuccess = () => resolve(req.result);
		req.onerror = () => reject(req.error);
	}).catch((error) => {
		dbPromise = null;

		throw error;
	}));
}

function tx(
	mode: IDBTransactionMode,
	fn: (store: IDBObjectStore) => IDBRequest
): Promise<void> {
	return openDb().then(
		(db) =>
			new Promise((resolve, reject) => {
				const transaction = db.transaction(STORE, mode);
				const request = fn(transaction.objectStore(STORE));

				request.onerror = () => reject(request.error);
				transaction.oncomplete = () => resolve();
				transaction.onabort = () => reject(transaction.error);
				transaction.onerror = () => reject(transaction.error);
			})
	);
}

function listAll(): Promise<PersistedLocalRecord[]> {
	return openDb().then(
		(db) =>
			new Promise((resolve, reject) => {
				const req = db.transaction(STORE, 'readonly').objectStore(STORE).getAll();

				req.onsuccess = () => resolve((req.result as PersistedLocalRecord[]) ?? []);
				req.onerror = () => reject(req.error);
			})
	);
}

class LocalFilesStore {
	/** All open local files, newest first (restored entries prepended on boot). */
	entries = $state<LocalFileEntry[]>([]);

	/** Opens a file: creates its object URL and persists the record. */
	add(file: File): Promise<void> {
		if (!file.type.startsWith('video/') && !file.type.startsWith('audio/')) {
			toast.error(t('localFile.unsupported'));

			return Promise.resolve();
		}

		const entry: LocalFileEntry = {
			file,
			blobUrl: URL.createObjectURL(file),
			id: `local-${Date.now()}-${Math.random().toString(36).slice(2)}`,
			addedAt: Date.now()
		};

		this.entries = [entry, ...this.entries];

		return this._persist(entry);
	}

	/** Closes a file: releases its object URL and drops its record. */
	remove(id: string): void {
		const entry = this.entries.find((e) => e.id === id);

		if (entry) {
			URL.revokeObjectURL(entry.blobUrl);
		}
		this.entries = this.entries.filter((e) => e.id !== id);
		void tx('readwrite', (store) => store.delete(id)).catch(() => {});
	}

	/** Looks an entry up by id (undefined once removed). */
	byId(id: string): LocalFileEntry | undefined {
		return this.entries.find((e) => e.id === id);
	}

	/** Total bytes held for open local files (what Settings shows as "stored
	 *  size" — the actual blob payloads in IndexedDB). */
	get usedBytes(): number {
		return this.entries.reduce((total, entry) => total + entry.file.size, 0);
	}

	/** Replaces (or clears) a file's resolved subtitle and persists it. */
	setSubtitle(id: string, track: SubtitleTrackResult | null): Promise<void> {
		const entry = this.byId(id);

		if (!entry) {
			return Promise.resolve();
		}
		entry.subtitle = track;

		return this._persist(entry);
	}

	/** Replaces (or clears) a file's finished audio split and persists it. */
	setAudioSplit(id: string, audioSplit: AudioSplitDone | null): Promise<void> {
		const entry = this.byId(id);

		if (!entry) {
			return Promise.resolve();
		}
		entry.audioSplit = audioSplit;

		return this._persist(entry);
	}

	/** Rebuilds entries from IndexedDB after a refresh. Blob URLs are gone,
	 *  so re-create them; resolved subtitles and audio splits ride along on
	 *  the same records. Best-effort: an unavailable store simply restores
	 *  nothing. */
	async restore(): Promise<void> {
		try {
			const saved = await listAll();

			if (saved.length === 0) {
				return;
			}
			const restored: LocalFileEntry[] = saved.map(
				({ id, file, addedAt, subtitle, audioSplit }) => ({
					file,
					id,
					blobUrl: URL.createObjectURL(file),
					addedAt: addedAt ?? Date.now(),
					subtitle: subtitle ?? null,
					audioSplit: audioSplit ?? null
				})
			);

			this.entries = [...restored, ...this.entries];
		} catch {
			// Best-effort — see module docstring.
		}
	}

	/** Closes every open file, revokes every blob URL, and clears the DB. */
	async clear(): Promise<void> {
		for (const entry of this.entries) {
			URL.revokeObjectURL(entry.blobUrl);
		}
		this.entries = [];

		try {
			const saved = await listAll();

			for (const { id } of saved) {
				await tx('readwrite', (store) => store.delete(id)).catch(() => {});
			}
		} catch {
			// Best-effort — see module docstring.
		}
	}

	private _persist(entry: LocalFileEntry): Promise<void> {
		// $state deep-proxies objects held in `entries`; structuredClone (and so
		// IndexedDB) can't clone a proxy, so snapshot into plain values first.
		const record = $state.snapshot({
			id: entry.id,
			file: entry.file,
			addedAt: entry.addedAt,
			subtitle: entry.subtitle ?? null,
			audioSplit: entry.audioSplit ?? null
		});

		return tx('readwrite', (store) => store.put(record)).catch(() => {
			// Best-effort — see module docstring.
		});
	}
}

export const localFiles = new LocalFilesStore();