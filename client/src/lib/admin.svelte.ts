/**
 * Admin panel API client + session state.
 *
 * The panel is English-only on purpose: backend messages and log lines are
 * English, and an ops tool reads better untranslated than half-translated.
 * Session is an HttpOnly cookie set by /admin/login — nothing stored in
 * localStorage (security: don't hand a stolen script an admin token).
 */

import { SvelteURLSearchParams } from 'svelte/reactivity';

import { API_BASE_URL } from '$lib/config';

export const adminSession = $state({
	checked: false,
	loggedIn: false,
	username: ''
});

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
	const res = await fetch(`${API_BASE_URL}${path}`, {
		...init,
		headers: { 'Content-Type': 'application/json', ...init.headers }
	});
	let body: unknown = null;

	try {
		body = await res.json();
	} catch {
		/* non-JSON error body */
	}

	if (!res.ok) {
		const detail = (body as { detail?: string })?.detail;

		throw new Error(detail || `Request failed (${res.status})`);
	}

	return body as T;
}

export function adminGet<T>(path: string, params?: Record<string, string | number>): Promise<T> {
	const qs = params
		? `?${new SvelteURLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)])).toString()}`
		: '';

	return request<T>(`${path}${qs}`, { method: 'GET' });
}

export function adminPost<T>(path: string, body: unknown = {}): Promise<T> {
	return request<T>(path, { method: 'POST', body: JSON.stringify(body) });
}

export function adminPut<T>(path: string, body: unknown): Promise<T> {
	return request<T>(path, { method: 'PUT', body: JSON.stringify(body) });
}

export function adminDelete<T>(path: string, params: Record<string, string>): Promise<T> {
	const qs = new SvelteURLSearchParams(params).toString();

	return request<T>(`${path}?${qs}`, { method: 'DELETE' });
}

export async function checkSession(): Promise<void> {
	try {
		const me = await request<{ username: string }>('/admin/me', { method: 'GET' });

		adminSession.loggedIn = true;
		adminSession.username = me.username;
	} catch {
		adminSession.loggedIn = false;
		adminSession.username = '';
	} finally {
		adminSession.checked = true;
	}
}

export async function login(username: string, password: string): Promise<void> {
	await request<{ ok: boolean }>('/admin/login', {
		method: 'POST',
		body: JSON.stringify({ username, password })
	});
	adminSession.loggedIn = true;
	adminSession.username = username;
}

export async function logout(): Promise<void> {
	try {
		await request('/admin/logout', { method: 'POST' });
	} finally {
		adminSession.loggedIn = false;
		adminSession.username = '';
	}
}

/** Minimal SSE consumer: `onMessage` gets every parsed `data:` payload. */
export async function adminEventStream(
	path: string,
	onMessage: (data: unknown) => void,
	signal: AbortSignal
): Promise<void> {
	const res = await fetch(`${API_BASE_URL}${path}`, { signal });

	if (!res.ok || !res.body) {
		return;
	}
	const reader = res.body.getReader();
	const decoder = new TextDecoder();
	let buffer = '';

	while (true) {
		const { done, value } = await reader.read();

		if (done) {
			return;
		}
		buffer += decoder.decode(value, { stream: true });
		const events = buffer.split('\n\n');

		buffer = events.pop() ?? '';
		for (const event of events) {
			const dataLine = event.split('\n').find((line) => line.startsWith('data: '));

			if (dataLine) {
				try {
					onMessage(JSON.parse(dataLine.slice(6)));
				} catch {
					/* malformed SSE payload — skip */
				}
			}
		}
	}
}
