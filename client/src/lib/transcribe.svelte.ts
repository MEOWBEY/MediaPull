/**
 * Transcription (auto-subtitles) controller — the single entry point the UI
 * uses to generate subtitles for an already-extracted video. Speech-to-text
 * only, via the server's Groq Whisper pipeline (no translation). Owns the SSE
 * subscription, cancellation, and error/toast feedback so components stay
 * thin. Mirrors `ExtractionController`'s shape (extraction.svelte.ts).
 */

import { toast } from 'svelte-sonner';

import {
	cancelTranscription,
	startTranscription,
	startTranscriptionLocal,
	type TranscribeSource
} from '$lib/api/transcribe';
import { resolveApiUrl } from '$lib/config';
import { i18n } from '$lib/i18n/index.svelte';
import {
	fetchAndParseVtt,
	revokeTrackUrls,
	segmentsToSrtUrl,
	segmentsToVttUrl
} from '$lib/subtitle-utils';
import type { SubtitleTrackResult, TranscribeStatus } from '$lib/types';

export type { SubtitleTrackResult } from '$lib/types';

/** What a generation run takes: the URL-based source shape (proxied quality
 *  URLs + optional duration) or a local file uploaded to `/transcribe/local`. */
export type TranscribeRequest = TranscribeSource | { kind: 'file'; file: File };

const { t } = i18n;

// The server now streams real, continuous progress over SSE: acquisition
// reports ffmpeg's transcode position (or download bytes) against the
// video's duration roughly twice a second, and every transcribed chunk
// pushes its own tick. The trickle survives only as a visual smoother for
// the sub-second gaps between those real updates -- and as the sole source
// of motion in the one case the server genuinely can't measure (an HLS
// source whose duration the client didn't know either). It eases the
// *displayed* value toward a ceiling barely ahead of the last real server
// value; a genuine update (or the terminal done/error state) always wins
// immediately -- it never invents completion, only motion toward it.
const TRICKLE_INTERVAL_MS = 250;
// How far ahead of the last real server value the ceiling is allowed to
// drift before another real update arrives -- keeps the trickle honest
// (it never claims to be almost done on its own). Tight, because real
// updates are frequent now: the displayed number should essentially BE the
// server's number.
const TRICKLE_LOOKAHEAD = 0.02;
const TRICKLE_MAX = 0.97;
// Fraction of the remaining gap (to the ceiling) closed per tick -- smaller
// = slower creep, since it's an ease-out (asymptotic, never quite arrives).
const TRICKLE_EASE = 0.05;

/** Localized stage text from the job's machine-readable fields. The server's
 *  own `stepLabel` string is English-only; the client rebuilds the label from
 *  `status` + chunk counters so it follows the app locale (and updates live
 *  if the user switches language mid-job). */
function stageLabel(status: TranscribeStatus): string {
	// The transcribing stage always renders its "x of y" counter regardless of
	// which path produced it, so handle it up front from the counters.
	if (status.status === 'transcribing' || status.detail === 'transcribing') {
		return (status.chunksTotal ?? 0) > 1
			? t('subtitles.stage.transcribingChunks', {
					done: status.chunksDone ?? 0,
					total: status.chunksTotal ?? 0
				})
			: t('subtitles.stage.transcribing');
	}

	// Prefer the fine-grained `detail` sub-stage when the server sends one --
	// it's more specific than `status` (e.g. extracting vs downloading_source,
	// building_subtitles vs dialogue_map). Falls back to `status` on older servers.
	switch (status.detail) {
		case 'planning':
			return t('subtitles.stage.planning');
		case 'downloading_source':
			return t('subtitles.stage.downloadingSource');
		case 'extracting':
			// No per-chunk counter here: in the windowed path extraction and
			// transcription overlap and share the chunk counters, so the count
			// belongs to the transcribing label, not this one.
			return t('subtitles.stage.extracting');
		case 'compressing':
			return t('subtitles.stage.compressing');
		case 'building_subtitles':
			return t('subtitles.stage.finalizing');
		case 'dialogue_map':
		case 'waveform': // older servers send this instead of 'dialogue_map'
			return t('subtitles.stage.dialogueMap');
	}

	switch (status.status) {
		case 'queued':
			return t('subtitles.stage.queued');
		case 'downloading':
			return t('subtitles.stage.downloading');
		case 'chunking':
			return t('subtitles.stage.chunking');
		case 'finalizing':
			return t('subtitles.stage.finalizing');
		default:
			// Terminal states (done/error/cancelled) never show a stage label --
			// the UI switches to its own result/error rendering.
			return '';
	}
}

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

	async generate(source: TranscribeRequest): Promise<void> {
		// Supersede any job still in flight: abort it, close its stream, and
		// clear its trickle timer so the old run can't keep writing into this
		// shared state — and tell the server to free the old job's slot.
		this.controller?.abort();
		this.stopStream();
		this.stopTrickle();
		if (this.jobId) {
			void cancelTranscription(this.jobId).catch(() => {});
		}

		const controller = new AbortController();

		this.controller = controller;
		this.error = null;
		this.progress = 0;
		this.serverProgress = 0;
		this.isRunning = true;
		this.jobId = null;

		const isLocalFile = 'file' in source;

		this.stepLabel = isLocalFile ? t('subtitles.stage.uploading') : t('subtitles.generating');
		this.startTrickle();

		try {
			const result = isLocalFile
				? await this.runLocalJob((source as { file: File }).file, controller.signal)
				: await this.runJob(source as TranscribeSource);

			if (controller.signal.aborted) {
				return;
			}

			revokeTrackUrls(this.track);
			this.track = result;
			this.progress = 1;
		} catch (err) {
			if (controller.signal.aborted) {
				return;
			}

			const message = err instanceof Error ? err.message : t('subtitles.error.generic');

			this.error = message;
			toast.error(message);
		} finally {
			if (this.controller === controller) {
				this.isRunning = false;
				this.stopStream();
				this.stopTrickle();
			}
		}
	}

	private runLocalJob(file: File, signal: AbortSignal): Promise<SubtitleTrackResult> {
		return new Promise((resolve, reject) => {
			startTranscriptionLocal(file, { signal })
				.then(({ jobId }) => {
					this.jobId = jobId;
					const es = new EventSource(resolveApiUrl(`/transcribe/${jobId}/events`));

					this.eventSource = es;
					// Reuse the same SSE handler as the URL-based path
					this._attachEventSource(es, resolve, reject);
				})
				.catch(reject);
		});
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

					const es = new EventSource(resolveApiUrl(`/transcribe/${jobId}/events`));

					this.eventSource = es;
					this._attachEventSource(es, resolve, reject);
				})
				.catch(reject);
		});
	}

	private _attachEventSource(
		es: EventSource,
		resolve: (r: SubtitleTrackResult) => void,
		reject: (e: unknown) => void
	): void {
		es.onmessage = (ev) => {
			let status: TranscribeStatus;

			try {
				status = JSON.parse(ev.data);
			} catch {
				return;
			}

			this.serverProgress = status.progress;
			this.progress = Math.max(this.progress, status.progress);
			this.stepLabel = stageLabel(status) || this.stepLabel;

			if (status.status === 'error') {
				this.stopStream();
				reject(new Error(status.error || t('subtitles.error.generic')));

				return;
			}

			if (status.status === 'cancelled') {
				this.stopStream();
				this.controller?.abort();
				reject(new Error('Transcription cancelled'));

				return;
			}

			if (status.status === 'done' && status.result) {
				this.stopStream();

				const { language } = status.result;
				const serverVttUrl = resolveApiUrl(status.result.vttUrl);
				const serverSrtUrl = resolveApiUrl(status.result.srtUrl);
				const dialogueMap = status.result.dialogueMap ?? status.result.waveform ?? null;

				fetchAndParseVtt(serverVttUrl)
					.then((segments) => {
						if (segments.length) {
							resolve({
								language,
								segments,
								vttUrl: segmentsToVttUrl(segments),
								srtUrl: segmentsToSrtUrl(segments),
								dialogueMap
							});

							return;
						}
						resolve({
							language,
							segments,
							vttUrl: serverVttUrl,
							srtUrl: serverSrtUrl,
							dialogueMap
						});
					})
					.catch(() =>
						resolve({
							language,
							segments: [],
							vttUrl: serverVttUrl,
							srtUrl: serverSrtUrl,
							dialogueMap
						})
					);
			}
		};

		es.onerror = () => {
			if (es.readyState === EventSource.CLOSED) {
				this.stopStream();
				reject(new Error(t('subtitles.error.generic')));
			}
		};
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
