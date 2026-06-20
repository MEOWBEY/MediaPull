/**
 * Tiny runes-based i18n. One reactive `locale`, a `t()` lookup, and helpers to
 * drive `dir`/`lang` on <html>. No dependency — the app only has two locales.
 */

import { browser } from '$app/environment';

import { DICTIONARIES, LOCALES, type Locale, type MessageKey } from './dictionaries';

const STORAGE_KEY = 'locale';

function initialLocale(): Locale {
	if (!browser) {return 'en';}

	const saved = localStorage.getItem(STORAGE_KEY);

	if (saved === 'en' || saved === 'fa') {return saved;}

	// Fall back to the browser language (fa-IR → fa), else English.
	return navigator.language?.toLowerCase().startsWith('fa') ? 'fa' : 'en';
}

class I18nStore {
	locale = $state<Locale>(initialLocale());

	get dir(): 'ltr' | 'rtl' {
		return LOCALES.find((l) => l.code === this.locale)?.dir ?? 'ltr';
	}

	get isRtl(): boolean {
		return this.dir === 'rtl';
	}

	/**
	 * Translate a key for the current locale, falling back to English.
	 * Optional `params` replace `{name}` placeholders in the message, so count
	 * and filename toasts read naturally in either language.
	 */
	t = (key: MessageKey, params?: Record<string, string | number>): string => {
		const table = DICTIONARIES[this.locale] ?? DICTIONARIES.en;
		let out = table[key] ?? DICTIONARIES.en[key] ?? key;

		if (params) {
			for (const [name, value] of Object.entries(params)) {
				out = out.replaceAll(`{${name}}`, String(value));
			}
		}

		return out;
	};

	setLocale(next: Locale): void {
		this.locale = next;

		if (browser) {
			localStorage.setItem(STORAGE_KEY, next);
		}
	}

	toggle(): void {
		this.setLocale(this.locale === 'en' ? 'fa' : 'en');
	}
}

export const i18n = new I18nStore();

/** Convenience: a stable `t` reference for components. */
export const {t} = i18n;

export { LOCALES, type Locale, type MessageKey };
