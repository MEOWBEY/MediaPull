/**
 * Tiny TTL cache with an in-memory layer and an optional localStorage layer.
 *
 * The client mirrors the server's result cache so that re-extracting a URL the
 * user just looked up is instant and makes no network request at all.
 */

import { browser } from '$app/environment';

interface Entry<T> {
	value: T;
	expiresAt: number;
}

export interface CacheOptions {
	/** Time-to-live in milliseconds. */
	ttl?: number;
	/** Max in-memory entries (LRU eviction). */
	maxEntries?: number;
	/** Persist to localStorage under this key prefix. Omit for memory-only. */
	persistKey?: string;
}

export class TTLCache<T> {
	private readonly ttl: number;
	private readonly maxEntries: number;
	private readonly persistKey?: string;
	private readonly memory = new Map<string, Entry<T>>();

	constructor(options: CacheOptions = {}) {
		this.ttl = options.ttl ?? 5 * 60 * 1000;
		this.maxEntries = options.maxEntries ?? 100;
		this.persistKey = options.persistKey;
	}

	get(key: string): T | null {
		const hit = this.memory.get(key) ?? this.readPersisted(key);

		if (!hit) {return null;}

		if (hit.expiresAt < Date.now()) {
			this.delete(key);

			return null;
		}

		// refresh LRU ordering
		this.memory.delete(key);
		this.memory.set(key, hit);

		return hit.value;
	}

	set(key: string, value: T): void {
		const entry: Entry<T> = { value, expiresAt: Date.now() + this.ttl };

		this.memory.set(key, entry);

		while (this.memory.size > this.maxEntries) {
			const oldest = this.memory.keys().next().value;

			if (oldest === undefined) {break;}
			this.memory.delete(oldest);
		}

		this.writePersisted(key, entry);
	}

	delete(key: string): void {
		this.memory.delete(key);

		if (browser && this.persistKey) {
			try {
				localStorage.removeItem(this.storageKey(key));
			} catch {
				/* ignore quota / privacy-mode errors */
			}
		}
	}

	private storageKey(key: string): string {
		return `${this.persistKey}:${key}`;
	}

	private readPersisted(key: string): Entry<T> | null {
		if (!browser || !this.persistKey) {return null;}

		try {
			const raw = localStorage.getItem(this.storageKey(key));

			if (!raw) {return null;}

			const entry = JSON.parse(raw) as Entry<T>;

			this.memory.set(key, entry);

			return entry;
		} catch {
			return null;
		}
	}

	private writePersisted(key: string, entry: Entry<T>): void {
		if (!browser || !this.persistKey) {return;}

		try {
			localStorage.setItem(this.storageKey(key), JSON.stringify(entry));
		} catch {
			/* ignore quota / privacy-mode errors */
		}
	}
}
