import { browser } from '$app/environment';
import type { Preferences } from '$lib/types';

const STORAGE_KEY = 'preferences';

export const DEFAULT_PREFERENCES: Preferences = {
	theme: 'system',
	layoutList: 'grid',
	videoSortField: 'quality',
	videoSortOrder: 'desc',
	enableAnimations: true,
	enableCompact: false,
	enableProxyForVideoExtract: true,
	enableVideoMute: false,
	enableVideoPreloadMetadata: false,
	showVideoThumbnail: true,
	showHlsTypeDownloadButton: false,
	showVideoOnlyFormats: false,
	autoOpenSubtitlePanel: false,
	contentTypeMode: 'auto'
};

export class PreferencesStore {
	current = $state<Preferences>({ ...DEFAULT_PREFERENCES });

	constructor() {
		if (browser) {
			this.load();
		}
	}

	update(patch: Partial<Preferences>): void {
		Object.assign(this.current, patch);
		this.persist();
	}

	reset(): void {
		Object.assign(this.current, DEFAULT_PREFERENCES);
		if (browser) {
			localStorage.removeItem(STORAGE_KEY);
		}
	}

	private load(): void {
		try {
			const raw = localStorage.getItem(STORAGE_KEY);

			if (raw) {
				Object.assign(this.current, JSON.parse(raw));
			}
		} catch (error) {
			console.warn('Failed to load preferences:', error);
		}
	}

	private persist(): void {
		if (!browser) {
			return;
		}

		try {
			localStorage.setItem(STORAGE_KEY, JSON.stringify(this.current));
		} catch (error) {
			console.warn('Failed to save preferences:', error);
		}
	}
}
