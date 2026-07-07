/**
 * Typed client for the SvelteKit `/api/*` routes.
 *
 * Responsibilities:
 *  - one place that knows the wire shape (`ApiEnvelope`)
 *  - normalized errors (`ApiError`) with a stable `.aborted` flag
 *  - per-call timeout + caller-supplied AbortSignal (linked)
 *  - in-flight de-duplication so double-clicks share one request
 *
 * `post()` is specific to the `/extract-videos`-style `{success, video}`
 * envelope. `postJson()`/`getJson()` are for endpoints with their own
 * purpose-built response shape (e.g. `/transcribe`'s job status) — they
 * return the parsed body as-is instead of unwrapping `.video`.
 */

import { API_BASE_URL } from '$lib/config';
import type { ApiEnvelope } from '$lib/types';

export class ApiError extends Error {
	readonly aborted: boolean;
	readonly status?: number;

	constructor(message: string, options: { aborted?: boolean; status?: number } = {}) {
		super(message);
		this.name = 'ApiError';
		this.aborted = options.aborted ?? false;
		this.status = options.status;
	}
}

interface PostOptions {
	signal?: AbortSignal;
	timeoutMs?: number;
}

const DEFAULT_TIMEOUT = 3 * 60 * 1000; // extraction + link validation can take a while

const inFlight = new Map<string, Promise<unknown>>();

/**
 * Pull the most descriptive message out of an error body. Our handlers send
 * `{success:false, error}`, but raw FastAPI failures (`HTTPException`, 422
 * validation) send `detail` — a string, or an array of `{msg}`. Reading only
 * `error`/`details` collapsed those to "Request failed (500)"; this surfaces the
 * real reason (e.g. the classified extractor message).
 */
function errorMessage(data: Partial<ApiEnvelope<unknown>>, status: number): string {
	if (data.error) {return data.error;}
	if (data.details) {return data.details;}

	const { detail } = data;

	if (typeof detail === 'string' && detail) {return detail;}
	if (Array.isArray(detail)) {
		const msg = detail.map((d) => d?.msg).filter(Boolean).join(', ');

		if (msg) {return msg;}
	}

	return `Request failed (${status})`;
}

function linkSignals(timeoutMs: number, external?: AbortSignal): { signal: AbortSignal; cancel: () => void } {
	const controller = new AbortController();
	const timer = setTimeout(() => controller.abort(new DOMException('Timeout', 'AbortError')), timeoutMs);

	const onAbort = () => controller.abort(external?.reason);

	if (external) {
		if (external.aborted) {onAbort();}
		else {external.addEventListener('abort', onAbort, { once: true });}
	}

	return {
		signal: controller.signal,
		cancel: () => {
			clearTimeout(timer);
			external?.removeEventListener('abort', onAbort);
		}
	};
}

async function doFetch(
	endpoint: string,
	init: RequestInit,
	options: PostOptions
): Promise<{ data: unknown; status: number; ok: boolean }> {
	const { signal, cancel } = linkSignals(options.timeoutMs ?? DEFAULT_TIMEOUT, options.signal);

	try {
		const response = await fetch(`${API_BASE_URL}${endpoint}`, { ...init, signal });

		let data: unknown;

		try {
			data = await response.json();
		} catch {
			throw new ApiError(`Server returned an invalid response (${response.status})`, {
				status: response.status
			});
		}

		return { data, status: response.status, ok: response.ok };
	} catch (error) {
		if (error instanceof ApiError) {throw error;}

		if (error instanceof DOMException && error.name === 'AbortError') {
			throw new ApiError('Request cancelled', { aborted: true });
		}

		throw new ApiError(error instanceof Error ? error.message : 'Network error');
	} finally {
		cancel();
	}
}

async function rawPost<T>(endpoint: string, body: unknown, options: PostOptions): Promise<T> {
	const { data, status, ok } = await doFetch(
		endpoint,
		{ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) },
		options
	);
	const envelope = data as Partial<ApiEnvelope<T>>;

	if (!ok || !envelope.success) {
		throw new ApiError(errorMessage(envelope, status), { status });
	}

	return envelope.video as T;
}

/** POST with in-flight de-duplication keyed by endpoint+body. */
export function post<T>(endpoint: string, body: unknown, options: PostOptions = {}): Promise<T> {
	const key = `POST ${endpoint}:${JSON.stringify(body)}`;
	const existing = inFlight.get(key);

	if (existing) {return existing as Promise<T>;}

	const promise = rawPost<T>(endpoint, body, options).finally(() => inFlight.delete(key));

	inFlight.set(key, promise);

	return promise;
}

async function rawJson<T>(
	endpoint: string,
	init: RequestInit,
	options: PostOptions
): Promise<T> {
	const { data, status, ok } = await doFetch(endpoint, init, options);

	if (!ok) {
		throw new ApiError(errorMessage(data as Partial<ApiEnvelope<unknown>>, status), { status });
	}

	return data as T;
}

/** POST returning the raw JSON body (no `{success, video}` envelope). */
export function postJson<T>(endpoint: string, body: unknown, options: PostOptions = {}): Promise<T> {
	const key = `POST ${endpoint}:${JSON.stringify(body)}`;
	const existing = inFlight.get(key);

	if (existing) {return existing as Promise<T>;}

	const promise = rawJson<T>(
		endpoint,
		{ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) },
		options
	).finally(() => inFlight.delete(key));

	inFlight.set(key, promise);

	return promise;
}

/** GET returning the raw JSON body. Not de-duplicated — each call (e.g. a
 *  poll tick) is its own independent request; a poll loop already awaits
 *  each one before firing the next, so there's nothing to collapse. */
export function getJson<T>(endpoint: string, options: PostOptions = {}): Promise<T> {
	return rawJson<T>(endpoint, { method: 'GET' }, options);
}
