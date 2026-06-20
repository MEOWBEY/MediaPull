/**
 * Extraction controller — the single entry point the UI uses to run link
 * extraction. Owns cancellation, the elapsed timer, client-side result caching,
 * and toast feedback so components stay thin.
 */

import { toast } from 'svelte-sonner';

import { ApiError, post } from '$lib/api/client';
import { TTLCache } from '$lib/cache';
import { i18n } from '$lib/i18n/index.svelte';
import { appStore } from '$lib/stores/app-state.svelte';
import type { IncomingVideo } from '$lib/types';

const { t } = i18n;

const extractCache = new TTLCache<IncomingVideo>({
	ttl: 5 * 60 * 1000,
	maxEntries: 50,
	persistKey: 'cache:extract'
});

function normalizeUrl(raw: string): string | null {
	const trimmed = raw?.trim();

	if (!trimmed) {
		toast.error(t('toast.invalidUrlEmpty'));

		return null;
	}

	try {
		return new URL(trimmed).toString();
	} catch {
		toast.error(t('toast.invalidUrl'));

		return null;
	}
}

/** Split a raw field value into individual URLs (whitespace/newline separated). */
function splitUrls(raw: string): string[] {
	return (raw ?? '')
		.split(/\s+/)
		.map((s) => s.trim())
		.filter(Boolean);
}

export class ExtractionController {
	elapsedSeconds = $state(0);

	// Batch/queue progress (0 when not running a batch).
	batchTotal = $state(0);
	batchDone = $state(0);

	private controller: AbortController | null = null;
	private timer: ReturnType<typeof setInterval> | null = null;
	private batchAborted = false;

	get isExtracting(): boolean {
		return appStore.isVideoExtractRunning;
	}

	get isRunning(): boolean {
		return this.isExtracting;
	}

	/** Public entry: route a single URL or a pasted batch to the right path. */
	async extract(raw: string): Promise<void> {
		const urls = splitUrls(raw);

		if (urls.length > 1) {
			return this.extractMany(urls);
		}

		await this.extractLinks(raw);
	}

	/** Process multiple URLs sequentially (deduped), one at a time. */
	async extractMany(rawUrls: string[]): Promise<void> {
		// One-shot dedupe of the pasted batch — not reactive state, so a plain Set is fine.
		// eslint-disable-next-line svelte/prefer-svelte-reactivity
		const urls = Array.from(new Set(splitUrls(rawUrls.join(' '))));

		if (!urls.length) {return;}
		if (urls.length === 1) {
			await this.extractLinks(urls[0]);

			return;
		}

		this.batchAborted = false;
		this.batchTotal = urls.length;
		this.batchDone = 0;

		let ok = 0;
		let failed = 0;

		for (const url of urls) {
			if (this.batchAborted) {break;}

			// Silent per-item: a 20-URL batch shouldn't fire 20 toasts or flash the
			// error alert for each miss. We tally the outcome and summarize at the end.
			const success = await this.extractLinks(url, { silent: true });

			if (success) {ok++;} else {failed++;}
			this.batchDone++;
		}

		const aborted = this.batchAborted;

		this.batchTotal = 0;
		this.batchDone = 0;

		if (aborted) {return;}

		if (failed === 0) {
			toast.success(t('toast.batchDone', { n: ok }));
		} else {
			toast.warning(t('toast.batchPartial', { ok, failed }));
		}
	}

	/**
	 * Extract links for one URL. Returns true on success. `silent` suppresses the
	 * per-item toast + error-alert state so a batch can report a single summary
	 * instead of one toast (and a lingering alert) per URL.
	 */
	async extractLinks(rawUrl: string, opts: { silent?: boolean } = {}): Promise<boolean> {
		const url = normalizeUrl(rawUrl);

		if (!url) {return false;}

		const cached = extractCache.get(url);

		if (cached) {
			appStore.addVideoExtractResultsToStore(cached);
			if (!opts.silent) {
				toast.success(t('toast.loadedCache', { n: cached.formats?.length ?? 0 }));
			}

			return true;
		}

		return this.run({
			silent: opts.silent,
			task: (signal) => post<IncomingVideo>('/extract-videos', { url }, { signal }),
			onSuccess: (video) => {
				extractCache.set(url, video);
				appStore.addVideoExtractResultsToStore(video);

				if (!opts.silent) {
					const count = video?.formats?.length ?? 0;

					toast.success(count === 1 ? t('toast.foundOne') : t('toast.foundMany', { n: count }));
				}
			}
		});
	}

	cancel(): void {
		this.batchAborted = true;
		this.stop();
		appStore.isVideoExtractRunning = false;
		toast.info(t('toast.cancelled'));
	}

	private async run<T>(config: {
		silent?: boolean;
		task: (signal: AbortSignal) => Promise<T>;
		onSuccess: (result: T) => void;
	}): Promise<boolean> {
		this.start();
		appStore.isVideoExtractRunning = true;
		appStore.videoExtractError = null;

		try {
			const result = await config.task(this.controller!.signal);

			if (this.controller?.signal.aborted) {return false;}

			config.onSuccess(result);

			return true;
		} catch (error) {
			if (error instanceof ApiError && error.aborted) {return false;}

			const message = error instanceof Error ? error.message : t('toast.unknownError');

			// In silent (batch) mode, don't pin the error alert or toast per item —
			// the caller tallies failures and shows one summary.
			if (!config.silent) {
				appStore.videoExtractError = message;
				toast.error(message);
			}

			return false;
		} finally {
			appStore.isVideoExtractRunning = false;
			this.stop();
		}
	}

	private start(): void {
		this.controller = new AbortController();
		this.elapsedSeconds = 0;
		this.timer = setInterval(() => this.elapsedSeconds++, 1000);
	}

	private stop(): void {
		this.controller?.abort();
		this.controller = null;

		if (this.timer) {
			clearInterval(this.timer);
			this.timer = null;
		}
	}
}

export const extraction = new ExtractionController();
