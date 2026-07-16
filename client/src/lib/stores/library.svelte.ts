import { browser } from '$app/environment';
import { createProxyToken } from '$lib/api/proxy-token';
import { buildProxiedUrl } from '$lib/proxy-url';
import { groupGalleriesBySource, groupVideosByQuality, maxFilesize, maxResolution } from '$lib/transform';
import type {
	GroupedGallery,
	GroupedVideo,
	IncomingGallery,
	IncomingVideo,
	Preferences,
	SubtitleTrackResult
} from '$lib/types';

import type { CookieStore } from './cookies.svelte';
import type { PreferencesStore } from './preferences.svelte';

const MAX_ENTRIES = 50;
const KEY_EXTRACT = 'videoExtractResults';
const KEY_GALLERIES = 'galleryExtractResults';

/** Whether two entries point at the same source. Prefer the source page URL
 *  (stable across re-extraction and independent of which input URL variant the
 *  user pasted); fall back to `id`. When neither is known we can't be sure, so
 *  treat them as different rather than risk hiding a genuinely new result. */
function sameSource(
	a: { webpage_url?: string; id?: string },
	b: { webpage_url?: string; id?: string }
): boolean {
	if (a.webpage_url && b.webpage_url) {
		return a.webpage_url === b.webpage_url;
	}
	if (a.id && b.id) {
		return a.id === b.id;
	}

	return false;
}

function sortVideos(items: GroupedVideo[], preferences: Preferences): GroupedVideo[] {
	const sorted = [...items].sort((a, b) => {
		let comparison = 0;

		switch (preferences.videoSortField) {
			case 'name':
				comparison = (a.title ?? '').localeCompare(b.title ?? '');
				break;
			case 'size':
				comparison = maxFilesize(a) - maxFilesize(b);
				break;
			case 'quality':
				comparison = maxResolution(a) - maxResolution(b);
				break;
		}

		return preferences.videoSortOrder === 'desc' ? -comparison : comparison;
	});

	return sorted;
}

export class LibraryStore {
	extractResults = $state<GroupedVideo[]>([]);
	galleryResults = $state<GroupedGallery[]>([]);

	constructor(private readonly preferences: PreferencesStore) {
		if (browser) {this.load();}
	}

	get sortedExtractResults(): GroupedVideo[] {
		return sortVideos(this.extractResults, this.preferences.current);
	}

	/** Adds a freshly extracted video to the library. Returns `true` if it was
	 *  actually added, `false` when an entry for the same source is already
	 *  present (the caller then shows an "already in your library" toast instead
	 *  of appending a duplicate card). `allowDuplicate` is for the refresh flow,
	 *  which appends the fresh result *then* removes the stale one -- there the
	 *  temporary duplicate is intended, so dedupe must not skip it. */
	addExtractResult(video: IncomingVideo, opts: { allowDuplicate?: boolean } = {}): boolean {
		const incoming = groupVideosByQuality([video]);

		if (!opts.allowDuplicate) {
			const fresh = incoming.filter(
				(v) => !this.extractResults.some((existing) => sameSource(existing, v))
			);

			if (!fresh.length) {
				return false;
			}
			this.extractResults.push(...fresh);
		} else {
			this.extractResults.push(...incoming);
		}

		this.evictOldest(this.extractResults);
		this.persist(KEY_EXTRACT, this.extractResults);

		return true;
	}

	/** Keep only the most recent MAX_ENTRIES, dropping the oldest (front). */
	private evictOldest(items: unknown[]): void {
		if (items.length > MAX_ENTRIES) {
			items.splice(0, items.length - MAX_ENTRIES);
		}
	}

	removeExtractResult(target: GroupedVideo): void {
		const index = this.extractResults.indexOf(target);

		if (index === -1) {return;}
		this.extractResults.splice(index, 1);
		this.persist(KEY_EXTRACT, this.extractResults);
	}

	/** Persists a resolved subtitle track directly on the stored card so it
	 *  survives a refresh -- mutating the object in place (rather than
	 *  replacing the array) keeps every other view's reference to it valid. */
	setSubtitleTrack(target: GroupedVideo, track: SubtitleTrackResult | null): void {
		const item = this.extractResults.find((v) => v === target);

		if (!item) {return;}

		item.subtitleTrack = track ?? undefined;
		this.persist(KEY_EXTRACT, this.extractResults);
	}

	clearExtractResults(): void {
		this.extractResults = [];
		this.remove(KEY_EXTRACT);
	}

	/** Mirrors `addExtractResult` for galleries -- see it for the dedupe /
	 *  `allowDuplicate` contract. */
	addGalleryResult(gallery: IncomingGallery, opts: { allowDuplicate?: boolean } = {}): boolean {
		const incoming = groupGalleriesBySource([gallery]);

		if (!opts.allowDuplicate) {
			const fresh = incoming.filter(
				(g) => !this.galleryResults.some((existing) => sameSource(existing, g))
			);

			if (!fresh.length) {
				return false;
			}
			this.galleryResults.push(...fresh);
		} else {
			this.galleryResults.push(...incoming);
		}

		this.evictOldest(this.galleryResults);
		this.persist(KEY_GALLERIES, this.galleryResults);

		return true;
	}

	removeGalleryResult(target: GroupedGallery): void {
		const index = this.galleryResults.indexOf(target);

		if (index === -1) {return;}
		this.galleryResults.splice(index, 1);
		this.persist(KEY_GALLERIES, this.galleryResults);
	}

	clearGalleryResults(): void {
		this.galleryResults = [];
		this.remove(KEY_GALLERIES);
	}

	clearAll(): void {
		this.clearExtractResults();
		this.clearGalleryResults();
	}

	get stats(): { extracted: number; galleries: number } {
		return { extracted: this.extractResults.length, galleries: this.galleryResults.length };
	}

	private load(): void {
		try {
			const extract = localStorage.getItem(KEY_EXTRACT);
			const parsedExtract = extract ? JSON.parse(extract) : null;

			if (Array.isArray(parsedExtract)) {
				// Drop pre-refactor cached entries (old shape had flat `type`/
				// `qualities` instead of `formatGroups`) rather than rendering them broken.
				this.extractResults = parsedExtract.filter((v) => Array.isArray(v?.formatGroups));
			}

			const galleries = localStorage.getItem(KEY_GALLERIES);
			const parsedGalleries = galleries ? JSON.parse(galleries) : null;

			if (Array.isArray(parsedGalleries)) {
				this.galleryResults = parsedGalleries.filter((g) => Array.isArray(g?.images));
			}
		} catch (error) {
			console.warn('Failed to load library:', error);
		}
	}

	/**
	 * Re-mint short-lived proxy cookie tokens for library items that have
	 * Settings cookies for their host. Persisted `ctok` values die after ~1h
	 * or a server restart; this rebuilds proxied URLs on app load.
	 */
	async remintProxyTokens(cookies: CookieStore): Promise<void> {
		if (!browser) {
			return;
		}

		let videosChanged = false;
		for (const video of this.extractResults) {
			const page = video.webpage_url;
			if (!page) {
				continue;
			}
			const text = cookies.matchFor(page);
			if (!text) {
				continue;
			}
			const token = await createProxyToken(text);
			if (!token) {
				continue;
			}
			const headers = { Referer: page };
			for (const group of video.formatGroups ?? []) {
				for (const q of group.qualities ?? []) {
					if (!q.sourceVideoUrl) {
						continue;
					}
					q.proxiedVideoUrl =
						buildProxiedUrl(q.sourceVideoUrl, headers, q.protocol, token) || q.proxiedVideoUrl;
					videosChanged = true;
				}
			}
		}

		let galleriesChanged = false;
		for (const gallery of this.galleryResults) {
			const page = gallery.webpage_url;
			if (!page) {
				continue;
			}
			const text = cookies.matchFor(page);
			if (!text) {
				continue;
			}
			const token = await createProxyToken(text);
			if (!token) {
				continue;
			}
			const headers = { Referer: page };
			for (const image of gallery.images ?? []) {
				if (!image.sourceUrl) {
					continue;
				}
				image.url = buildProxiedUrl(image.sourceUrl, headers, 'https', token) || image.url;
				galleriesChanged = true;
			}
		}

		if (videosChanged) {
			this.persist(KEY_EXTRACT, this.extractResults);
		}
		if (galleriesChanged) {
			this.persist(KEY_GALLERIES, this.galleryResults);
		}
	}

	private persist(key: string, data: unknown): void {
		if (!browser) {return;}

		try {
			localStorage.setItem(key, JSON.stringify(data));
		} catch (error) {
			console.warn(`Failed to save ${key}:`, error);
		}
	}

	private remove(key: string): void {
		if (browser) {localStorage.removeItem(key);}
	}
}
