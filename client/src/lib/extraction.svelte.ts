/**
 * Extraction controller — the single entry point the UI uses to run link
 * extraction. Owns cancellation, the elapsed timer, client-side result caching,
 * and toast feedback so components stay thin.
 */

import { toast } from 'svelte-sonner';

import { ApiError, post, postGallery } from '$lib/api/client';
import { resolveGalleryCookieTokens, resolveVideoCookieTokens } from '$lib/api/proxy-token';
import { TTLCache } from '$lib/cache';
import { i18n } from '$lib/i18n/index.svelte';
import { appStore } from '$lib/stores/app-state.svelte';
import type { IncomingGallery, IncomingVideo } from '$lib/types';

const { t } = i18n;

const extractCache = new TTLCache<IncomingVideo>({
	ttl: 5 * 60 * 1000,
	maxEntries: 50,
	persistKey: 'cache:extract'
});

const galleryExtractCache = new TTLCache<IncomingGallery>({
	ttl: 5 * 60 * 1000,
	maxEntries: 50,
	persistKey: 'cache:extract-gallery'
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

		if (!urls.length) {
			return;
		}
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
			if (this.batchAborted) {
				break;
			}

			// Silent per-item: a 20-URL batch shouldn't fire 20 toasts or flash the
			// error alert for each miss. We tally the outcome and summarize at the end.
			const success = await this.extractLinks(url, { silent: true });

			if (success) {
				ok++;
			} else {
				failed++;
			}
			this.batchDone++;
		}

		const aborted = this.batchAborted;

		this.batchTotal = 0;
		this.batchDone = 0;

		if (aborted) {
			return;
		}

		if (failed === 0) {
			toast.success(t('toast.batchDone', { n: ok }));
		} else {
			toast.warning(t('toast.batchPartial', { ok, failed }));
		}
	}

	/**
	 * Extract links for one URL. Returns true on success. `silent` suppresses the
	 * per-item toast + error-alert state so a batch can report a single summary
	 * instead of one toast (and a lingering alert) per URL. `forceRefresh` skips
	 * (and evicts) any cached result -- for re-pulling a source whose direct
	 * links may have expired, where serving the stale cache would defeat the point.
	 * `mode` overrides the persisted content-type preference for this one call
	 * -- used by `retryAsOtherType` for a manual "try the other type" action.
	 * When the preference is `'auto'` (the default) and no `mode` override is
	 * given, tries video first and silently falls back to gallery -- see
	 * `extractAuto`.
	 */
	async extractLinks(
		rawUrl: string,
		opts: { silent?: boolean; forceRefresh?: boolean; mode?: 'video' | 'gallery' } = {}
	): Promise<boolean> {
		const mode = opts.mode ?? appStore.preferences.contentTypeMode;

		if (mode === 'auto') {
			return this.extractAuto(rawUrl, opts);
		}

		return mode === 'gallery'
			? this.extractGalleryLinks(rawUrl, opts)
			: this.extractVideoLinks(rawUrl, opts);
	}

	/** Auto-detect: try video first (the more common case), and only if that
	 *  comes back empty/fails, silently retry as a gallery -- no error toast/
	 *  alert for the first attempt, since failing over is the expected path
	 *  for an image-only page, not a real error. */
	private async extractAuto(
		rawUrl: string,
		opts: { silent?: boolean; forceRefresh?: boolean } = {}
	): Promise<boolean> {
		const gotVideo = await this.extractVideoLinks(rawUrl, { ...opts, silentError: true });

		if (gotVideo) {
			return true;
		}

		return this.extractGalleryLinks(rawUrl, opts);
	}

	private async extractVideoLinks(
		rawUrl: string,
		opts: { silent?: boolean; silentError?: boolean; forceRefresh?: boolean } = {}
	): Promise<boolean> {
		const url = normalizeUrl(rawUrl);

		if (!url) {
			return false;
		}

		// Per-site auth cookies (if the user added any for this host). Sent only
		// for the matching domain; bucket the cache so authed/anon results don't mix.
		const cookies = appStore.cookies.matchFor(url);
		const cacheKey = cookies ? `${url}#auth` : url;

		if (opts.forceRefresh) {
			extractCache.delete(cacheKey);
		}

		const cached = opts.forceRefresh ? null : extractCache.get(cacheKey);

		if (cached) {
			const added = appStore.addVideoExtractResultsToStore(cached, {
				allowDuplicate: opts.forceRefresh
			});

			if (!opts.silent) {
				toast.success(
					added
						? t('toast.loadedCache', { n: cached.formats?.length ?? 0 })
						: t('toast.alreadyInLibrary')
				);
			}

			return true;
		}

		return this.run({
			silent: opts.silent,
			silentError: opts.silentError,
			task: async (signal) => {
				const video = await post<IncomingVideo>(
					'/extract-videos',
					cookies ? { url, cookies } : { url },
					{ signal }
				);

				// Swap any auth cookies for opaque tokens before the result is
				// cached or turned into (shareable) proxy URLs.
				await resolveVideoCookieTokens(video);

				return video;
			},
			onSuccess: (video) => {
				extractCache.set(cacheKey, video);
				const added = appStore.addVideoExtractResultsToStore(video, {
					allowDuplicate: opts.forceRefresh
				});

				if (!opts.silent) {
					if (!added) {
						toast.success(t('toast.alreadyInLibrary'));

						return;
					}
					const count = video?.formats?.length ?? 0;

					toast.success(count === 1 ? t('toast.foundOne') : t('toast.foundMany', { n: count }));
				}
			}
		});
	}

	private async extractGalleryLinks(
		rawUrl: string,
		opts: { silent?: boolean; forceRefresh?: boolean } = {}
	): Promise<boolean> {
		const url = normalizeUrl(rawUrl);

		if (!url) {
			return false;
		}

		const cookies = appStore.cookies.matchFor(url);
		const cacheKey = cookies ? `${url}#auth` : url;

		if (opts.forceRefresh) {
			galleryExtractCache.delete(cacheKey);
		}

		const cached = opts.forceRefresh ? null : galleryExtractCache.get(cacheKey);

		if (cached) {
			const added = appStore.addGalleryExtractResultsToStore(cached, {
				allowDuplicate: opts.forceRefresh
			});

			if (!opts.silent) {
				toast.success(
					added
						? t('toast.loadedCacheImages', { n: cached.images?.length ?? 0 })
						: t('toast.alreadyInLibrary')
				);
			}

			return true;
		}

		return this.run({
			silent: opts.silent,
			task: async (signal) => {
				const gallery = await postGallery<IncomingGallery>(
					'/extract-gallery',
					cookies ? { url, cookies } : { url },
					{ signal }
				);

				await resolveGalleryCookieTokens(gallery);

				return gallery;
			},
			onSuccess: (gallery) => {
				galleryExtractCache.set(cacheKey, gallery);
				const added = appStore.addGalleryExtractResultsToStore(gallery, {
					allowDuplicate: opts.forceRefresh
				});

				if (!opts.silent) {
					if (!added) {
						toast.success(t('toast.alreadyInLibrary'));

						return;
					}
					const count = gallery?.images?.length ?? 0;

					toast.success(
						count === 1 ? t('toast.foundOneImage') : t('toast.foundManyImages', { n: count })
					);

					if (gallery?.skippedCount) {
						toast.warning(t('gallery.someSkipped', { n: gallery.skippedCount }));
					}
				}
			}
		});
	}

	/** Manual "wrong type" escape hatch: re-extracts the same URL through the
	 *  other endpoint, bypassing the persisted content-type preference for this
	 *  one call. `extractAuto` handles the common case (auto mode guessing
	 *  wrong) on its own; this is for forcing a specific type on demand. */
	async retryAsOtherType(rawUrl: string, currentMode: 'video' | 'gallery'): Promise<boolean> {
		const otherMode = currentMode === 'video' ? 'gallery' : 'video';

		return this.extractLinks(rawUrl, { mode: otherMode, forceRefresh: true });
	}

	cancel(): void {
		this.batchAborted = true;
		this.stop();
		appStore.isVideoExtractRunning = false;
		toast.info(t('toast.cancelled'));
	}

	private async run<T>(config: {
		silent?: boolean;
		silentError?: boolean;
		task: (signal: AbortSignal) => Promise<T>;
		onSuccess: (result: T) => void;
	}): Promise<boolean> {
		this.start();
		appStore.isVideoExtractRunning = true;
		appStore.videoExtractError = null;

		const signal = this.controller?.signal;

		if (!signal) {
			// start() always sets controller before this runs, but guard defensively.
			appStore.isVideoExtractRunning = false;
			this.stop();

			return false;
		}

		try {
			const result = await config.task(signal);

			if (this.controller?.signal.aborted) {
				return false;
			}

			config.onSuccess(result);

			return true;
		} catch (error) {
			if (error instanceof ApiError && error.aborted) {
				return false;
			}

			const message = error instanceof Error ? error.message : t('toast.unknownError');

			// In silent (batch) mode, don't pin the error alert or toast per item —
			// the caller tallies failures and shows one summary. `silentError`
			// additionally covers auto-mode's first (video) attempt, where a
			// failure is expected/normal (it just means "try gallery next"), not
			// something worth alarming the user about.
			if (!config.silent && !config.silentError) {
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
		// Single-flight: abort any request still in flight before starting a new
		// one, so a rapid re-paste / retry doesn't leak the prior fetch (it would
		// run to the 3-min server timeout and confuse the running flag).
		this.controller?.abort();
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
