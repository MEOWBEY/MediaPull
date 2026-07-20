/**
 * Application store facade.
 *
 * Composes the focused `PreferencesStore` and `LibraryStore` and exposes the
 * stable surface the components consume. Extraction run state lives here because
 * it is cross-cutting UI session state.
 */

import type {
	GroupedGallery,
	GroupedVideo,
	IncomingGallery,
	IncomingVideo,
	Preferences,
	SubtitleTrackResult
} from '$lib/types';

import { CookieStore } from './cookies.svelte';
import { LibraryStore } from './library.svelte';
import { PreferencesStore } from './preferences.svelte';

/** A recoverable extract failure: the URL that failed, the message shown, and
 *  the content-type mode that was attempted. */
export type ExtractFailure = {
	url: string;
	message: string;
	mode: 'auto' | 'video' | 'gallery';
};

export type {
	GroupedGallery,
	GroupedVideo,
	IncomingGallery,
	IncomingVideo,
	Preferences,
	VideoFormat,
	VideoMetadata
} from '$lib/types';

class AppStore {
	private readonly prefs = new PreferencesStore();
	private readonly library = new LibraryStore();
	private readonly cookieStore = new CookieStore();

	isVideoExtractRunning = $state(false);

	videoExtractError = $state<string | null>(null);

	/** The most recent non-silent extract failure, kept so the error banner can
	 *  offer Retry / Open cookies / Try the other type. `mode` is what was
	 *  attempted ('auto' tries both). Cleared on any new run and on success. */
	lastFailure = $state<ExtractFailure | null>(null);

	get preferences(): Preferences {
		return this.prefs.current;
	}

	/** Per-site auth cookies (Settings → Cookies). Sensitive; browser-only. */
	get cookies(): CookieStore {
		return this.cookieStore;
	}

	get videoExtractResults(): GroupedVideo[] {
		return this.library.extractResults;
	}

	/** Returns false when an entry for the same source already exists (caller
	 *  shows an "already in library" toast instead of appending a duplicate).
	 *  `allowDuplicate` is used by the refresh flow -- see `LibraryStore`. */
	addVideoExtractResultsToStore(data: IncomingVideo, opts: { allowDuplicate?: boolean } = {}): boolean {
		return this.library.addExtractResult(data, opts);
	}

	removeVideoExtractResultFromStore(target: GroupedVideo): void {
		this.library.removeExtractResult(target);
	}

	get galleries(): GroupedGallery[] {
		return this.library.galleryResults;
	}

	addGalleryExtractResultsToStore(data: IncomingGallery, opts: { allowDuplicate?: boolean } = {}): boolean {
		return this.library.addGalleryResult(data, opts);
	}

	removeGalleryExtractResultFromStore(target: GroupedGallery): void {
		this.library.removeGalleryResult(target);
	}

	/** Persists a generated/reused subtitle track on the card itself, so a page
	 *  refresh doesn't lose it (and removing the video drops it automatically). */
	setSubtitleTrackForVideo(target: GroupedVideo, track: SubtitleTrackResult | null): void {
		this.library.setSubtitleTrack(target, track);
	}

	clearVideoExtractResultsFromStore(): void {
		this.library.clearExtractResults();
	}

	updatePreferences(updates: Partial<Preferences>): void {
		this.prefs.update(updates);
	}

	clearErrors(): void {
		this.videoExtractError = null;
		this.lastFailure = null;
	}

	reset(): void {
		this.library.clearAll();
		this.clearErrors();
		this.prefs.reset();
	}

	getStats(): { extracted: number; galleries: number } {
		return this.library.stats;
	}

	/** Re-mint proxy cookie tokens for library items (call once on app load). */
	async remintLibraryProxyTokens(): Promise<void> {
		await this.library.remintProxyTokens(this.cookieStore);
	}
}

export const appStore = new AppStore();
