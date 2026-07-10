/**
 * Resolves which subtitle track (if any) a player should show -- either
 * generated via `TranscriptionController` (Groq speech-to-text) or picked
 * from a caption the source already provides. Owns the state VideoPlayer
 * used to hold directly; VideoPlayer keeps only the DOM-touching `$effect`s
 * that react to `track` (they need `videoEl`/`playerRootEl`, which live on
 * the component, not here). Mirrors `TranscriptionController`'s shape
 * (transcribe.svelte.ts).
 */

import { toast } from 'svelte-sonner';

import type { TranscribeSource } from '$lib/api/transcribe';
import { i18n } from '$lib/i18n/index.svelte';
import { fetchAndParseVtt, segmentsToVttUrl } from '$lib/subtitle-utils';
import { TranscriptionController } from '$lib/transcribe.svelte';
import type { SubtitleSegment, SubtitleTrack, SubtitleTrackResult } from '$lib/types';

const { t } = i18n;

export class SubtitleResolver {
	private transcription = new TranscriptionController();

	// Set directly when the user picks a track the source already provides (no
	// pipeline needed); otherwise mirrors the Groq job's result once it
	// finishes. Existing-track pick wins if both are set.
	existingTrack = $state<SubtitleTrackResult | null>(null);
	// True while an existing source caption is being fetched/parsed -- distinct
	// from `isRunning` (the Groq job) since it never has a meaningful progress
	// percentage.
	resolvingExisting = $state(false);

	get track(): SubtitleTrackResult | null {
		return this.existingTrack ?? this.transcription.track;
	}

	get isRunning(): boolean {
		return this.transcription.isRunning;
	}

	get progress(): number {
		return this.transcription.progress;
	}

	/** Human-readable current pipeline stage ("Transcribing... (3 of 8 done)"). */
	get stepLabel(): string {
		return this.transcription.stepLabel;
	}

	/** The in-flight Groq job's id, if any -- see `TranscriptionController.currentJobId`. */
	get currentJobId(): string | null {
		return this.transcription.currentJobId;
	}

	/** Restores a track persisted from a previous session -- whether it came
	 *  from Groq or an existing caption doesn't matter once resolved, so it
	 *  slots into the same place a freshly-generated one would. The persisted
	 *  vttUrl may be dead by now (a generated track's URL dies with the
	 *  server job's TTL; a source caption URL can expire), so rebuild it from
	 *  the segments we still have -- they're the durable part. */
	restore(track: SubtitleTrackResult | null): void {
		if (!track) {
			return;
		}

		// Blob URLs only exist in the browser -- during SSR keep the track
		// as-is (the browser-side mount re-restores it anyway).
		this.transcription.track =
			track.segments.length && typeof window !== 'undefined'
				? { ...track, vttUrl: segmentsToVttUrl(track.segments) }
				: track;
	}

	async generate(source: TranscribeSource): Promise<void> {
		await this.transcription.generate(source);

		// A freshly generated track must actually show up: if an earlier
		// existing-caption pick is still set (even a stale/empty one), it
		// would win the `track` getter above and hide the new result.
		if (this.transcription.track) {
			this.existingTrack = null;
		}
	}

	/** Cancels the Groq job in flight, if any -- a no-op otherwise, mirroring
	 *  the `resolvingExisting` guard in `useExisting()` above. */
	cancel(): void {
		if (!this.transcription.isRunning) {
			return;
		}

		this.transcription.cancel();
	}

	async useExisting(track: SubtitleTrack): Promise<boolean> {
		// Guards against the card's Subtitles button feeling unresponsive: the
		// fetch below can take a moment, and without this a second click before
		// it resolves would fire a redundant parallel fetch instead of just
		// waiting on the first one.
		if (this.resolvingExisting) {
			return false;
		}

		let segments: SubtitleSegment[] = [];

		this.resolvingExisting = true;
		try {
			// Our parser reads both WebVTT and SRT (they differ only in the cue
			// decimal separator). YouTube's non-vtt formats (json3/srv3/ttml) are
			// normalized to WebVTT server-side (see `_normalize_caption_url`), so
			// anything reaching here as vtt/srt is parseable.
			if (track.ext === 'vtt' || track.ext === 'srt') {
				try {
					segments = await fetchAndParseVtt(track.url);
				} catch {
					segments = [];
				}
			}
		} finally {
			this.resolvingExisting = false;
		}

		// A track with no usable cues is a failure, not a result: setting it
		// anyway used to leave the button "green" while both the panel and the
		// player showed nothing (an expired/blocked caption URL, or a format
		// the parser can't read). Surface the error and leave state untouched
		// so the user can retry or fall back to generating.
		if (!segments.length) {
			toast.error(t('subtitles.error.fetchFailed'));

			return false;
		}

		// Serve the native <track> from a blob built out of the parsed
		// segments rather than the upstream URL: the fetch above already
		// proved we have the full cue list, while the upstream URL can
		// independently fail for the browser's own <track> loader (expiring
		// signature, referer check) -- which showed captions in the panel but
		// never on the video.
		this.existingTrack = {
			language: track.lang,
			segments,
			vttUrl: segmentsToVttUrl(segments)
		};

		return true;
	}
}
