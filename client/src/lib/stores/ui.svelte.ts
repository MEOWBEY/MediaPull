/**
 * Cross-component UI state that isn't a user preference and isn't persisted.
 *
 * Currently the Preferences sheet's open flag (shared so the header's settings
 * button, the page-level dialog, and recovery actions all drive one source of
 * truth) plus an optional tab to deep-link into when opening it.
 */

export type PreferencesTab = 'general' | 'library' | 'playback' | 'cookies';

class UiStore {
	preferencesOpen = $state(false);
	// When a caller wants to land the user on a specific tab (e.g. the error
	// banner's "add cookies", the video-only note's "open settings"). Null =
	// leave the dialog on whatever tab it last showed. Consumed + cleared by
	// the dialog.
	preferencesTab = $state<PreferencesTab | null>(null);

	openPreferences(tab: PreferencesTab | null = null) {
		this.preferencesTab = tab;
		this.preferencesOpen = true;
	}
}

export const ui = new UiStore();
