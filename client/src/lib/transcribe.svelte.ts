/**
 * Transcription (auto-subtitles) controller — the single entry point the UI
 * uses to generate subtitles for an already-extracted video. Speech-to-text
 * only, via the server's Groq Whisper pipeline (no translation). Owns the SSE
 * subscription, cancellation, and error/toast feedback so components stay
 * thin. Mirrors `ExtractionController`'s shape (extraction.svelte.ts).
 */

import { toast } from 'svelte-sonner';

import { cancelTranscription, startTranscription, type TranscribeSource } from '$lib/api/transcribe';
import { resolveApiUrl } from '$lib/config';
import { i18n } from '$lib/i18n/index.svelte';
import { fetchAndParseVtt } from '$lib/subtitle-utils';
import type { SubtitleTrackResult, TranscribeStatus } from '$lib/types';

export type { SubtitleTrackResult } from '$lib/types';

const { t } = i18n;

// The server only reports a handful of discrete stage percentages (see
// `jobs.py`) with long, silent gaps in between -- e.g. "acquiring audio" sits
// at a flat 5% for however long the download+ffmpeg extraction actually
// takes, which for a long video reads as "stuck". A fake trickle fills the
// gap: it eases the *displayed* progress up toward a ceiling just ahead of
// the last real value the server reported, so there's always visible motion,
// while a genuine new server value (or the terminal done/error state) always
// wins immediately -- this never invents completion, only motion toward it.
// Real updates now arrive over SSE the instant the server has them (not up to
// 1.75s late, back when this was polled) -- during the transcribing stage
// especially, where each completed chunk pushes its own update, the trickle
// barely gets a chance to run at all. It still earns its keep for the
// still-genuinely-flat single-step stages (audio download/transcode), just
// with a tighter leash now that it's compensating for real gaps, not
// polling latency.
const TRICKLE_INTERVAL_MS = 250;
// How far ahead of the last real server value the ceiling is allowed to
// drift before another real update arrives -- keeps the trickle honest
// (it never claims to be almost done on its own).
const TRICKLE_LOOKAHEAD = 0.04;
const TRICKLE_MAX = 0.97;
// Fraction of the remaining gap (to the ceiling) closed per tick -- smaller
// = slower creep, since it's an ease-out (asymptotic, never quite arrives).
const TRICKLE_EASE = 0.05;

export class TranscriptionController {
	isRunning = $state(false);
	progress = $state(0);
	stepLabel = $state('');
	error = $state<string | null>(null);
	track = $state<SubtitleTrackResult | null>(null);

	private controller: AbortController | null = null;
	private eventSource: EventSource | null = null;
	private trickleTimer: ReturnType<typeof setInterval> | null = null;
	// Last value actually reported by the server -- the trickle ceiling and
	// the "never regress" floor are both derived from this, not from
	// `progress` itself (which the trickle nudges every 250ms).
	private serverProgress = 0;
	// Set once `startTranscription` resolves -- `cancel()` needs it to tell
	// the server to free the job's slot, not just abort locally.
	private jobId: string | null = null;

	/** The current job's id, if a generation is in flight -- used for a
	 *  best-effort `beforeunload` cancel beacon, which needs the raw id to
	 *  build its own keepalive request (the normal `cancel()` path isn't
	 *  reliable during page teardown). */
	get currentJobId(): string | null {
		return this.isRunning ? this.jobId : null;
	}

	async generate(source: TranscribeSource): Promise<void> {
		this.error = null;
		this.progress = 0;
		this.serverProgress = 0;
		this.stepLabel = t('subtitles.generating');
		this.isRunning = true;
		this.controller = new AbortController();
		this.jobId = null;
		this.startTrickle();

		try {
			this.track = await this.runJob(source);
			this.progress = 1;
		} catch (err) {
			if (this.controller.signal.aborted) {
				return;
			}

			const message = err instanceof Error ? err.message : t('subtitles.error.generic');

			this.error = message;
			toast.error(message);
		} finally {
			this.isRunning = false;
			this.stopStream();
			this.stopTrickle();
		}
	}

	cancel(): void {
		this.controller?.abort();
		this.isRunning = false;
		this.stopStream();
		this.stopTrickle();

		// Best-effort courtesy call -- fire-and-forget so the server frees the
		// job's slot instead of running it to completion for nobody. The local
		// abort above is what actually matters to the UI; a network error here
		// (offline, server already gone) shouldn't surface anywhere.
		if (this.jobId) {
			void cancelTranscription(this.jobId).catch(() => {});
		}
	}

	private runJob(source: TranscribeSource): Promise<SubtitleTrackResult> {
		return new Promise((resolve, reject) => {
			startTranscription(source, { signal: this.controller?.signal })
				.then(({ jobId }) => {
					this.jobId = jobId;

					// Native browser API -- no library needed. Auto-reconnects on a
					// dropped connection on its own; `onerror` below only treats it
					// as fatal once the browser itself gives up (readyState CLOSED),
					// not on every transient blip.
					const es = new EventSource(resolveApiUrl(`/transcribe/${jobId}/events`));

					this.eventSource = es;

					es.onmessage = (ev) => {
						let status: TranscribeStatus;

						try {
							status = JSON.parse(ev.data);
						} catch {
							return;
						}

						// The real value is a floor, never a regression -- the trickle
						// may already be displaying something higher within this stage's
						// look-ahead window, and jumping backward would look broken.
						this.serverProgress = status.progress;
						this.progress = Math.max(this.progress, status.progress);
						this.stepLabel = status.stepLabel;

						if (status.status === 'error') {
							this.stopStream();
							reject(new Error(status.error || t('subtitles.error.generic')));

							return;
						}

						// A server-side cancellation (e.g. triggered from another tab,
						// or a future admin action) -- handled the same way as a local
						// `cancel()` call: abort so `generate()`'s catch treats this as
						// a silent stop rather than an error to surface.
						if (status.status === 'cancelled') {
							this.stopStream();
							this.controller?.abort();
							reject(new Error('Transcription cancelled'));

							return;
						}

						if (status.status === 'done' && status.result) {
							this.stopStream();

							const { language } = status.result;
							const vttUrl = resolveApiUrl(status.result.vttUrl);
							const srtUrl = resolveApiUrl(status.result.srtUrl);

							// Subtitles still render via the native <track src> even if
							// this fetch-for-the-panel step fails.
							fetchAndParseVtt(vttUrl)
								.then((segments) => resolve({ language, segments, vttUrl, srtUrl }))
								.catch(() => resolve({ language, segments: [], vttUrl, srtUrl }));
						}
					};

					es.onerror = () => {
						if (es.readyState === EventSource.CLOSED) {
							this.stopStream();
							reject(new Error(t('subtitles.error.generic')));
						}
					};
				})
				.catch(reject);
		});
	}

	private startTrickle(): void {
		this.trickleTimer = setInterval(() => {
			// A backgrounded tab has nothing showing this value -- skip the
			// reactive write (and the re-render it'd trigger once the tab is
			// foregrounded again mid-transition) rather than creeping the
			// progress bar toward its ceiling for no visible audience.
			if (typeof document !== 'undefined' && document.hidden) {
				return;
			}

			const ceiling = Math.min(this.serverProgress + TRICKLE_LOOKAHEAD, TRICKLE_MAX);

			if (this.progress < ceiling) {
				this.progress += (ceiling - this.progress) * TRICKLE_EASE;
			}
		}, TRICKLE_INTERVAL_MS);
	}

	private stopTrickle(): void {
		if (this.trickleTimer) {
			clearInterval(this.trickleTimer);
			this.trickleTimer = null;
		}
	}

	private stopStream(): void {
		if (this.eventSource) {
			this.eventSource.close();
			this.eventSource = null;
		}
	}
}
