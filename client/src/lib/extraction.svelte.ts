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

// Memory-only — the library store is the durable copy (avoids dual localStorage).
const extractCache = new TTLCache<IncomingVideo>({
	ttl: 5 * 60 * 1000,
	maxEntries: 50
});

const galleryExtractCache = new TTLCache<IncomingGallery>({
	ttl: 5 * 60 * 1000,
	maxEntries: 50
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

// Hard cap on a single pasted batch. Each successful extract mounts a full
// video.js player, so an unbounded paste (hundreds of URLs) freezes/OOMs the
// tab. Anything past the cap is dropped with a heads-up toast rather than
// silently, so the user knows to split the list.
const MAX_BATCH = 20;

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
		const deduped = Array.from(new Set(splitUrls(rawUrls.join(' '))));

		if (!deduped.length) {
			return;
		}
		if (deduped.length === 1) {
			await this.extractLinks(deduped[0]);

			return;
		}

		// Cap the batch so a huge paste can't spawn hundreds of players and lock
		// the tab. Trim the overflow up front and tell the user what was dropped.
		const urls = deduped.slice(0, MAX_BATCH);
		const dropped = deduped.length - urls.length;

		if (dropped > 0) {
			toast.warning(t('toast.batchCapped', { max: MAX_BATCH, dropped }));
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
		opts: { silent?: boolean; forceRefresh?: boolean; mode?: 'auto' | 'video' | 'gallery' } = {}
	): Promise<boolean> {
		const mode = opts.mode ?? appStore.preferences.contentTypeMode;

		if (mode === 'auto') {
			return this.extractAuto(rawUrl, opts);
		}

		return mode === 'gallery'
			? this.extractGalleryLinks(rawUrl, opts)
			: this.extractVideoLinks(rawUrl, opts);
	}

	/** Hosts/paths that are almost always image galleries — try gallery first
	 *  so we skip a full failed video extract on Pinterest/Imgur/etc. */
	private looksLikeGalleryUrl(rawUrl: string): boolean {
		try {
			// eslint-disable-next-line svelte/prefer-svelte-reactivity
			const u = new URL(rawUrl.trim());
			const host = u.hostname.toLowerCase().replace(/^www\./, '');
			const path = u.pathname.toLowerCase();

			if (
				host.includes('pinterest.') ||
				host === 'imgur.com' ||
				host.endsWith('.imgur.com') ||
				host.includes('flickr.com') ||
				host.includes('vsco.co') ||
				host.includes('deviantart.com')
			) {
				return true;
			}
			if (path.includes('/gallery') || path.includes('/album') || path.includes('/a/')) {
				// Instagram /p/ and /reel/ are often video — only treat clear gallery paths.
				if (host.includes('instagram.com') || host.includes('youtube.com')) {
					return false;
				}

				return true;
			}

			return false;
		} catch {
			return false;
		}
	}

	/** Auto-detect: video first (common case), gallery fallback — unless the URL
	 *  looks like a pure gallery host, then reverse the order. First-attempt
	 *  failures are silent (failover is expected for the wrong content type). */
	private async extractAuto(
		rawUrl: string,
		opts: { silent?: boolean; forceRefresh?: boolean } = {}
	): Promise<boolean> {
		const galleryFirst = this.looksLikeGalleryUrl(rawUrl);
		const order: Array<'video' | 'gallery'> = galleryFirst
			? ['gallery', 'video']
			: ['video', 'gallery'];

		let firstError: string | null = null;
		let secondError: string | null = null;

		for (let i = 0; i < order.length; i++) {
			const kind = order[i];
			const onError = (message: string) => {
				if (i === 0) {
					firstError = message;
				} else {
					secondError = message;
				}
			};
			const ok =
				kind === 'gallery'
					? await this.extractGalleryLinks(rawUrl, {
							...opts,
							silentError: true,
							onError
						})
					: await this.extractVideoLinks(rawUrl, {
							...opts,
							silentError: true,
							onError
						});

			if (ok) {
				return true;
			}
		}

		// Prefer the video-path error when present (usually more specific).
		const message =
			(galleryFirst ? secondError ?? firstError : firstError ?? secondError) ??
			t('toast.unknownError');

		if (!opts.silent) {
			appStore.videoExtractError = message;
			appStore.lastFailure = { url: rawUrl.trim(), message, mode: 'auto' };
			toast.error(message);
		}

		return false;
	}

	private async extractVideoLinks(
		rawUrl: string,
		opts: {
			silent?: boolean;
			silentError?: boolean;
			forceRefresh?: boolean;
			onError?: (message: string) => void;
		} = {}
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
			onError: opts.onError,
			failureContext: { url, mode: 'video' },
			task: async (signal) => {
				const video = await post<IncomingVideo>(
					'/extract-videos',
					cookies ? { url, cookies } : { url },
					{ signal }
				);

				// Mint ctok from Settings cookies — extract JSON deliberately
				// omits Cookie headers (they would leak sessions on multi-user
				// deploys). Attach tokens before cache / proxy URL build.
				await resolveVideoCookieTokens(video, cookies);

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
		opts: {
			silent?: boolean;
			silentError?: boolean;
			forceRefresh?: boolean;
			onError?: (message: string) => void;
		} = {}
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
			silentError: opts.silentError,
			onError: opts.onError,
			failureContext: { url, mode: 'gallery' },
			task: async (signal) => {
				const gallery = await postGallery<IncomingGallery>(
					'/extract-gallery',
					cookies ? { url, cookies } : { url },
					{ signal }
				);

				await resolveGalleryCookieTokens(gallery, cookies);

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
					for (const w of gallery?.warnings ?? []) {
						const key =
							w.code === 'login'
								? 'gallery.warning.login'
								: w.code === 'rate_limit'
									? 'gallery.warning.rateLimit'
									: w.code === 'quality'
										? 'gallery.warning.quality'
										: w.code === 'truncated'
											? 'gallery.warning.truncated'
											: 'gallery.warning.generic';

						toast.warning(
							key === 'gallery.warning.generic'
								? t(key, { message: w.message })
								: t(key)
						);
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

	/** Re-run the last failed extract exactly as it was tried (same URL + mode).
	 *  Used by the error banner's Retry button. */
	async retryLastFailure(): Promise<void> {
		const failure = appStore.lastFailure;

		if (!failure) {
			return;
		}

		appStore.clearErrors();
		await this.extractLinks(failure.url, { mode: failure.mode, forceRefresh: true });
	}

	/** Force the opposite content type for the last failure. From an 'auto'
	 *  failure (which already tried both), `preferType` says which single type to
	 *  force next. Used by the banner's "Try as gallery/video" action. */
	async retryLastAsType(preferType: 'video' | 'gallery'): Promise<void> {
		const failure = appStore.lastFailure;

		if (!failure) {
			return;
		}

		appStore.clearErrors();
		await this.extractLinks(failure.url, { mode: preferType, forceRefresh: true });
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
		/** URL + mode of this attempt, so a non-silent failure can be stored as a
		 *  recoverable `lastFailure` (Retry / Open cookies / Try other type). */
		failureContext?: { url: string; mode: 'video' | 'gallery' };
		task: (signal: AbortSignal) => Promise<T>;
		onSuccess: (result: T) => void;
		/** Always invoked with the failure message, even when `silentError`/
		 *  `silent` suppress the toast/alert -- lets `extractAuto` capture the
		 *  video attempt's (more specific) error to show later if the gallery
		 *  fallback also fails, instead of losing it. */
		onError?: (message: string) => void;
	}): Promise<boolean> {
		const controller = this.start();

		appStore.isVideoExtractRunning = true;
		appStore.videoExtractError = null;

		const { signal } = controller;

		try {
			const result = await config.task(signal);

			if (signal.aborted) {
				return false;
			}

			config.onSuccess(result);

			return true;
		} catch (error) {
			if (error instanceof ApiError && error.aborted) {
				return false;
			}

			const message = error instanceof Error ? error.message : t('toast.unknownError');

			config.onError?.(message);

			// In silent (batch) mode, don't pin the error alert or toast per item —
			// the caller tallies failures and shows one summary. `silentError`
			// additionally covers auto-mode's first (video) attempt, where a
			// failure is expected/normal (it just means "try gallery next"), not
			// something worth alarming the user about.
			if (!config.silent && !config.silentError) {
				appStore.videoExtractError = message;
				if (config.failureContext) {
					appStore.lastFailure = {
						url: config.failureContext.url,
						message,
						mode: config.failureContext.mode
					};
				}
				toast.error(message);
			}

			return false;
		} finally {
			// Only the latest run may tear down the shared controller/timer/flag —
			// a newer start() owns them now, and aborting here would kill that
			// run's fetch and clear its running state out from under it.
			if (this.controller === controller) {
				appStore.isVideoExtractRunning = false;
				this.stop();
			}
		}
	}

	private start(): AbortController {
		// Single-flight: abort any request still in flight before starting a new
		// one, so a rapid re-paste / retry doesn't leak the prior fetch (it would
		// run until the client's ~3 min fetch timeout and confuse the running flag).
		this.controller?.abort();

		if (this.timer) {
			clearInterval(this.timer);
		}

		const controller = new AbortController();

		this.controller = controller;
		this.elapsedSeconds = 0;
		this.timer = setInterval(() => this.elapsedSeconds++, 1000);

		return controller;
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
