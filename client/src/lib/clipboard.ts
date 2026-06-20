/**
 * Clipboard helper with a non-secure-context fallback. The async Clipboard API
 * only exists in secure contexts (HTTPS). On a plain-http LAN address (common on
 * mobile) it's undefined, so fall back to a temporary textarea + execCommand so
 * copy still works.
 */

/** Write text to the clipboard. Returns true on success, false on any failure. */
export async function writeClipboard(text: string): Promise<boolean> {
	try {
		if (window.isSecureContext && navigator.clipboard?.writeText) {
			await navigator.clipboard.writeText(text);
		} else {
			const textarea = document.createElement('textarea');

			textarea.value = text;
			textarea.setAttribute('readonly', '');
			textarea.style.position = 'fixed';
			textarea.style.opacity = '0';
			document.body.appendChild(textarea);
			textarea.focus();
			textarea.select();

			const ok = document.execCommand('copy');

			document.body.removeChild(textarea);
			if (!ok) {
				throw new Error('execCommand copy failed');
			}
		}

		return true;
	} catch {
		return false;
	}
}
