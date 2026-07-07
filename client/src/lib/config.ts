/**
 * Client runtime config.
 *
 * `API_BASE_URL` is where the Python backend lives. In dev, leave
 * `VITE_API_BASE_URL` unset — requests stay relative and Vite's dev proxy (see
 * vite.config.ts) forwards them to the backend, so there's no CORS. For a
 * deployed static build, set `VITE_API_BASE_URL` to the backend origin.
 */

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/+$/, '');

/**
 * Resolve a backend-relative path (e.g. `/transcribe/{id}/subtitle.vtt`) to
 * an absolute URL. Needed anywhere the URL leaves a same-origin `fetch()`
 * context — a native `<track src>` element fetching the file directly —
 * since a bare relative path only resolves correctly when the request
 * itself originates from this page.
 */
export function resolveApiUrl(path: string): string {
	if (API_BASE_URL) {return `${API_BASE_URL}${path}`;}

	return typeof window === 'undefined' ? path : `${window.location.origin}${path}`;
}
