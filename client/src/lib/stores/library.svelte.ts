import { browser } from '$app/environment';
import { groupVideosByQuality, maxFilesize, maxResolution } from '$lib/transform';
import type { GroupedVideo, IncomingVideo, Preferences } from '$lib/types';

import type { PreferencesStore } from './preferences.svelte';

const MAX_ENTRIES = 50;
const KEY_EXTRACT = 'videoExtractResults';

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

	constructor(private readonly preferences: PreferencesStore) {
		if (browser) {this.load();}
	}

	get sortedExtractResults(): GroupedVideo[] {
		return sortVideos(this.extractResults, this.preferences.current);
	}

	addExtractResult(video: IncomingVideo): void {
		this.extractResults.push(...groupVideosByQuality([video]));
		this.evictOldest(this.extractResults);
		this.persist(KEY_EXTRACT, this.extractResults);
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

	clearExtractResults(): void {
		this.extractResults = [];
		this.remove(KEY_EXTRACT);
	}

	clearAll(): void {
		this.clearExtractResults();
	}

	get stats(): { extracted: number } {
		return { extracted: this.extractResults.length };
	}

	private load(): void {
		try {
			const extract = localStorage.getItem(KEY_EXTRACT);
			const parsedExtract = extract ? JSON.parse(extract) : null;

			if (Array.isArray(parsedExtract)) {this.extractResults = parsedExtract;}
		} catch (error) {
			console.warn('Failed to load library:', error);
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
