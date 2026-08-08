/**
 * Client for auto-generated subtitles: speech-to-text via the server's Groq
 * Whisper pipeline. Transcription only -- the audio's own spoken language,
 * no translation.
 *
 *  - `startTranscription()` kicks off `POST /transcribe`.
 *  - Progress is then read via an `EventSource` on `/transcribe/{jobId}/events`
 *    directly in `transcribe.svelte.ts` (native browser API, no wrapper
 *    needed here).
 *  - `cancelTranscription()` sends `DELETE /transcribe/{jobId}`.
 */

import { del, postJson, uploadFile } from '$lib/api/client';
import type { VideoFormat } from '$lib/types';

/** The bits of a `GroupedVideo` the transcription job needs -- accepted as
 *  its own shape so `VideoPlayer.svelte` can pass its flat props through. */
export interface TranscribeSource {
	webpageUrl?: string;
	/** The player's known duration -- the server uses it to turn ffmpeg's
	 *  transcode position into a real percentage (it can't cheaply probe an
	 *  HLS source's length itself). Optional; progress degrades gracefully. */
	durationSeconds?: number;
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
 * Send each quality's *proxied* URL, not the raw source. The server unwraps
 * `/proxy-video?...` for a direct origin fetch (avoids double-hop + HLS rewrite
 * issues), restores Referer/User-Agent from the query, and resolves opaque
 * `ctok` tokens back to Cookie headers via ProxyService.
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
		{
			webpage_url: source.webpageUrl ?? '',
			duration_seconds: source.durationSeconds || null,
			formats: toBackendFormats(source)
		},
		opts
	);
}

export function startTranscriptionLocal(
	file: File,
	opts: { signal?: AbortSignal } = {}
): Promise<{ jobId: string }> {
	return uploadFile<{ jobId: string }>('/transcribe/local', file, opts);
}

/**
 * `DELETE /transcribe/{jobId}` -- best-effort courtesy call so the backend
 * frees the job's slot instead of running it to completion for nobody. A 404
 * means the job is already gone or finished, which is exactly what cancelling
 * it would have achieved anyway, so it's treated as success rather than
 * thrown as an error.
 */
export async function cancelTranscription(jobId: string, opts: { signal?: AbortSignal } = {}): Promise<void> {
	const { status, ok } = await del(`/transcribe/${jobId}`, opts);

	if (!ok && status !== 404) {
		throw new Error(`Request failed (${status})`);
	}
}
