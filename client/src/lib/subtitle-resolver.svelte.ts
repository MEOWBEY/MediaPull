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
import { fetchAndParseVtt } from '$lib/subtitle-utils';
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

	/** The in-flight Groq job's id, if any -- see `TranscriptionController.currentJobId`. */
	get currentJobId(): string | null {
		return this.transcription.currentJobId;
	}

	/** Restores a track persisted from a previous session -- whether it came
	 *  from Groq or an existing caption doesn't matter once resolved, so it
	 *  slots into the same place a freshly-generated one would. */
	restore(track: SubtitleTrackResult | null): void {
		if (track) {
			this.transcription.track = track;
		}
	}

	async generate(source: TranscribeSource): Promise<void> {
		await this.transcription.generate(source);
	}

	/** Cancels the Groq job in flight, if any -- a no-op otherwise, mirroring
	 *  the `resolvingExisting` guard in `useExisting()` above. */
	cancel(): void {
		if (!this.transcription.isRunning) {
			return;
		}

		this.transcription.cancel();
	}

	async useExisting(track: SubtitleTrack): Promise<void> {
		// Guards against the card's Subtitles button feeling unresponsive: the
		// fetch below can take a moment, and without this a second click before
		// it resolves would fire a redundant parallel fetch instead of just
		// waiting on the first one.
		if (this.resolvingExisting) {
			return;
		}

		let segments: SubtitleSegment[] = [];

		this.resolvingExisting = true;
		try {
			// Native <track>/our own parser both need WebVTT; a non-vtt existing
			// track (e.g. YouTube's srv3/ttml formats) still isn't usable here.
			if (track.ext === 'vtt') {
				try {
					segments = await fetchAndParseVtt(track.url);
				} catch {
					// Surfaced rather than silently left empty -- otherwise a fetch
					// failure (network blip, an upstream URL that expired between
					// extraction and click) looks identical to "no captions" once the
					// panel opens, with nothing telling the user what happened.
					segments = [];
					toast.error(t('subtitles.error.fetchFailed'));
				}
			}
		} finally {
			this.resolvingExisting = false;
		}

		this.existingTrack = {
			language: track.lang,
			segments,
			vttUrl: track.ext === 'vtt' ? track.url : undefined
		};
	}
}
