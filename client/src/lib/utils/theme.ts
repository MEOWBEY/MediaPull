interface ThemePreferences {
	theme: 'light' | 'dark' | 'system';
	highContrast: boolean;
	compactMode: boolean;
	animationsEnabled: boolean;
}

class ThemeManager {
	applyTheme(preferences: ThemePreferences): void {
		if (typeof document === 'undefined') return;

		const root = document.documentElement;

		// Apply theme
		if (preferences.theme === 'dark') {
			root.classList.add('dark');
		} else if (preferences.theme === 'light') {
			root.classList.remove('dark');
		} else {
			// System theme
			const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
			if (isDark) root.classList.add('dark');
			else root.classList.remove('dark');
		}

		// Apply other preferences
		root.classList.toggle('high-contrast', preferences.highContrast);
		root.classList.toggle('compact-mode', preferences.compactMode);
		root.classList.toggle('no-animations', !preferences.animationsEnabled);
	}

	// Listen for system theme changes
	watchSystemTheme(preferences: ThemePreferences, callback: () => void): () => void {
		if (typeof window === 'undefined') return () => {};

		const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
		const handler = () => {
			if (preferences.theme === 'system') {
				this.applyTheme(preferences);
				callback();
			}
		};

		mediaQuery.addEventListener('change', handler);
		return () => mediaQuery.removeEventListener('change', handler);
	}
}

export const themeManager = new ThemeManager();