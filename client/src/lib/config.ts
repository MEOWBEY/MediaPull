/**
 * Client runtime config.
 *
 * `API_BASE_URL` is where the Python backend lives. In dev, leave
 * `VITE_API_BASE_URL` unset — requests stay relative and Vite's dev proxy (see
 * vite.config.ts) forwards them to the backend, so there's no CORS. For a
 * deployed static build, set `VITE_API_BASE_URL` to the backend origin.
 */

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/+$/, '');
