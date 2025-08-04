interface KeyboardHandlers {
	onExtract?: () => void;
	onCancel?: () => void;
	onTogglePreferences?: (show?: boolean) => void;
}

interface Preferences {
	keyboardShortcuts: boolean;
}

class KeyboardShortcutsManager {
	private cleanupFn: (() => void) | null = null;

	setup(preferences: Preferences, handlers: KeyboardHandlers): void {
		// Clean up existing listeners first
		this.cleanup();

		const handleKeydown = (e: KeyboardEvent) => {
			if (!preferences.keyboardShortcuts) return;

			if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
				e.preventDefault();
				handlers.onExtract?.();
			}
			if (e.key === 'Escape') {
				handlers.onCancel?.();
				handlers.onTogglePreferences?.(false);
			}
			if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
				e.preventDefault();
				document.getElementById('search-input')?.focus();
			}
			if ((e.ctrlKey || e.metaKey) && e.key === ',') {
				e.preventDefault();
				handlers.onTogglePreferences?.(true);
			}
		};

		document.addEventListener('keydown', handleKeydown);
		this.cleanupFn = () => document.removeEventListener('keydown', handleKeydown);
	}

	cleanup(): void {
		if (this.cleanupFn) {
			this.cleanupFn();
			this.cleanupFn = null;
		}
	}
}

export const keyboardShortcuts = new KeyboardShortcutsManager();