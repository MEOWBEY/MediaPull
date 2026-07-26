/**
 * Typed HTTP client for the Python FastAPI backend.
 *
 * In dev, leave `VITE_API_BASE_URL` unset so requests stay same-origin and
 * Vite's proxy (vite.config.ts) forwards `/extract-*`, `/proxy-*`,
 * `/transcribe`, `/health` to the backend — no CORS. In production, set
 * `VITE_API_BASE_URL` to the API origin when the SPA is hosted separately.
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
import type { ApiEnvelope, GalleryApiEnvelope } from '$lib/types';

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

interface InFlightEntry {
	promise: Promise<unknown>;
	/** Drives the shared fetch — aborted only once every attached caller has aborted. */
	controller: AbortController;
	/** Callers that could still abort and are waiting on the shared promise. */
	waiters: number;
}

const inFlight = new Map<string, InFlightEntry>();

/** Attach one caller to a shared in-flight request. The caller's own signal
 *  rejects only THAT caller's promise; the underlying fetch is aborted once
 *  every attached caller has aborted, so one caller unmounting/cancelling
 *  can't kill a request another still-mounted caller is waiting on. */
function attachCaller<T>(entry: InFlightEntry, signal?: AbortSignal): Promise<T> {
	const shared = entry.promise as Promise<T>;

	if (!signal) {return shared;}

	entry.waiters++;

	return new Promise<T>((resolve, reject) => {
		let settled = false;

		const onAbort = () => {
			if (settled) {return;}
			settled = true;
			if (--entry.waiters === 0) {entry.controller.abort(signal.reason);}
			reject(new ApiError('Request cancelled', { aborted: true }));
		};

		if (signal.aborted) {
			onAbort();

			return;
		}
		signal.addEventListener('abort', onAbort, { once: true });
		shared.then(
			(value) => {
				if (settled) {return;}
				settled = true;
				signal.removeEventListener('abort', onAbort);
				resolve(value);
			},
			(error) => {
				if (settled) {return;}
				settled = true;
				signal.removeEventListener('abort', onAbort);
				reject(error);
			}
		);
	});
}

/** Share one underlying request per key. The fetch runs on an internal
 *  signal (plus the first caller's timeout); each caller's AbortSignal is
 *  handled per-caller via `attachCaller`. */
function dedupe<T>(
	key: string,
	options: PostOptions,
	run: (options: PostOptions) => Promise<T>
): Promise<T> {
	let entry = inFlight.get(key);

	if (!entry) {
		const controller = new AbortController();
		const created: InFlightEntry = { controller, waiters: 0, promise: Promise.resolve() };

		created.promise = run({ timeoutMs: options.timeoutMs, signal: controller.signal }).finally(
			() => {
				if (inFlight.get(key) === created) {inFlight.delete(key);}
			}
		);
		// Callers observe rejections through their per-caller wrappers, which
		// detach on abort — this no-op handler keeps a rejection that lands
		// after every caller has aborted from surfacing as unhandled.
		void created.promise.catch(() => {});
		inFlight.set(key, created);
		entry = created;
	}

	return attachCaller<T>(entry, options.signal);
}

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
	return dedupe(`POST ${endpoint}:${JSON.stringify(body)}`, options, (opts) =>
		rawPost<T>(endpoint, body, opts)
	);
}

async function rawPostGallery<T>(endpoint: string, body: unknown, options: PostOptions): Promise<T> {
	const { data, status, ok } = await doFetch(
		endpoint,
		{ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) },
		options
	);
	const envelope = data as Partial<GalleryApiEnvelope<T>>;

	if (!ok || !envelope.success) {
		throw new ApiError(errorMessage(envelope as Partial<ApiEnvelope<unknown>>, status), { status });
	}

	return envelope.gallery as T;
}

/** Same contract as `post()` (in-flight dedup, timeout, envelope unwrapping)
 *  but for `/extract-gallery`-style responses, which wrap their payload
 *  under `gallery` instead of `video`. */
export function postGallery<T>(endpoint: string, body: unknown, options: PostOptions = {}): Promise<T> {
	return dedupe(`POST ${endpoint}:${JSON.stringify(body)}`, options, (opts) =>
		rawPostGallery<T>(endpoint, body, opts)
	);
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
	return dedupe(`POST ${endpoint}:${JSON.stringify(body)}`, options, (opts) =>
		rawJson<T>(
			endpoint,
			{ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) },
			opts
		)
	);
}

/** GET returning the raw JSON body. Not de-duplicated — each call (e.g. a
 *  poll tick) is its own independent request; a poll loop already awaits
 *  each one before firing the next, so there's nothing to collapse. */
export function getJson<T>(endpoint: string, options: PostOptions = {}): Promise<T> {
	return rawJson<T>(endpoint, { method: 'GET' }, options);
}

/**
 * DELETE with no response body expected (a 204 on success). Unlike
 * `rawJson`, this never calls `response.json()` — cancel-style endpoints
 * reply with an empty body, and `doFetch` would otherwise treat that as
 * "invalid response". Callers get the status code back directly so they can
 * decide what a given non-2xx (e.g. 404 = "already gone") means for them,
 * rather than this helper guessing on their behalf.
 */
export async function del(endpoint: string, options: PostOptions = {}): Promise<{ status: number; ok: boolean }> {
	const { signal, cancel } = linkSignals(options.timeoutMs ?? DEFAULT_TIMEOUT, options.signal);

	try {
		const response = await fetch(`${API_BASE_URL}${endpoint}`, { method: 'DELETE', signal });

		return { status: response.status, ok: response.ok };
	} catch (error) {
		if (error instanceof DOMException && error.name === 'AbortError') {
			throw new ApiError('Request cancelled', { aborted: true });
		}

		throw new ApiError(error instanceof Error ? error.message : 'Network error');
	} finally {
		cancel();
	}
}
