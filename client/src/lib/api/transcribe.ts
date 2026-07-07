/**
 * Client for auto-generated subtitles: speech-to-text via the server's Groq
 * Whisper pipeline. Transcription only -- the audio's own spoken language,
 * no translation.
 *
 *  - `startTranscription()` kicks off `POST /transcribe`.
 *  - `pollJobStatus()` polls `GET /transcribe/{jobId}` until done/error.
 */

import { getJson, postJson } from '$lib/api/client';
import type { TranscribeStatus, VideoFormat } from '$lib/types';

/** The bits of a `GroupedVideo` the transcription job needs -- accepted as
 *  its own shape so `VideoPlayer.svelte` can pass its flat props through. */
export interface TranscribeSource {
	webpageUrl?: string;
	qualities: Partial<VideoFormat>[];
}

interface BackendFormat {
	url: string;
	ext: string;
	tbr: number;
	format_id: string;
	protocol: string;
	resolution: number | null;
	video_only: boolean;
}

/**
 * Send each quality's *proxied* URL, not the raw source. `/proxy-video`
 * already replays the right Referer/Cookie/User-Agent (baked into its query
 * string by `buildProxiedUrl`), so the backend's audio download can GET it
 * directly with no extra headers -- reusing the proxy instead of
 * duplicating impersonation logic.
 */
function toBackendFormats(source: TranscribeSource): BackendFormat[] {
	return (source.qualities ?? [])
		.filter((q): q is Partial<VideoFormat> & { proxiedVideoUrl: string } => Boolean(q.proxiedVideoUrl))
		.map((q) => ({
			url: q.proxiedVideoUrl,
			ext: q.ext ?? '',
			tbr: q.tbr ?? 0,
			format_id: q.format_id ?? 'unknown',
			protocol: q.protocol ?? 'https',
			resolution: q.resolution || null,
			video_only: Boolean(q.videoOnly)
		}));
}

export function startTranscription(
	source: TranscribeSource,
	opts: { signal?: AbortSignal } = {}
): Promise<{ jobId: string }> {
	return postJson<{ jobId: string }>(
		'/transcribe',
		{ webpage_url: source.webpageUrl ?? '', formats: toBackendFormats(source) },
		opts
	);
}

export function pollJobStatus(jobId: string, opts: { signal?: AbortSignal } = {}): Promise<TranscribeStatus> {
	return getJson<TranscribeStatus>(`/transcribe/${jobId}`, opts);
}
