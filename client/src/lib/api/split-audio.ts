/**
 * Client for the split-audio endpoints (the feature is shown as "Split audio").
 *
 * - `splitAudioLocal(file)` — uploads a local file, server splits its audio off
 * - `splitAudioUrl(formats)` — server picks the smallest sound-bearing source
 *   out of the list, downloads it, and splits its audio off
 * - `pollSplitAudio(id)`    — one-shot status check (call in a loop until done)
 *
 * All requests go through the shared `$lib/api/client` helpers so they get
 * the same timeout/abort/envelope semantics as everything else.
 */

import { ApiError, getJson, postJson, uploadFile } from '$lib/api/client';
import { API_BASE_URL } from '$lib/config';
import type { VideoFormat } from '$lib/types';

export interface SplitAudioStatus {
	exportId: string;
	status: 'queued' | 'splitting' | 'done' | 'error';
	progress: number;
	error?: string | null;
	downloadUrl?: string | null;
	filename?: string | null;
	stepLabel?: string | null;
}

export function splitAudioLocal(
	file: File,
	opts: { signal?: AbortSignal } = {}
): Promise<{ exportId: string }> {
	return uploadFile<{ exportId: string }>('/split-audio/local', file, opts);
}

/**
 * Send each quality's *proxied* URL, not the raw source — the same contract
 * the transcription endpoint uses. The server picks the smallest
 * sound-bearing stream (the playback pick is often the biggest file),
 * unwraps `/proxy-video?...` back to the origin with Referer/Cookie/UA, and
 * falls back to an impersonated download on anti-bot CDNs.
 */
interface SplitAudioFormat {
	url: string;
	ext: string;
	tbr: number;
	format_id: string;
	protocol: string;
	resolution: number | null;
	video_only: boolean;
}

function toSplitFormats(qualities: Partial<VideoFormat>[]): SplitAudioFormat[] {
	return qualities
		.filter((q) => Boolean(q.proxiedVideoUrl || q.sourceVideoUrl))
		.map((q) => ({
			url: q.proxiedVideoUrl || q.sourceVideoUrl || '',
			ext: q.ext ?? '',
			tbr: q.tbr ?? 0,
			format_id: q.format_id ?? 'unknown',
			protocol: q.protocol ?? 'https',
			resolution: q.resolution || null,
			video_only: Boolean(q.videoOnly)
		}));
}

export function splitAudioUrl(
	qualities: Partial<VideoFormat>[],
	opts: { signal?: AbortSignal } = {}
): Promise<{ exportId: string }> {
	return postJson<{ exportId: string }>(
		'/split-audio/url',
		{ formats: toSplitFormats(qualities) },
		opts
	);
}

export function pollSplitAudio(
	exportId: string,
	opts: { signal?: AbortSignal } = {}
): Promise<SplitAudioStatus> {
	return getJson<SplitAudioStatus>(`/split-audio/${exportId}/status`, opts);
}

async function parseError(response: Response): Promise<string> {
	try {
		const body = await response.json();

		return body?.detail || body?.error || `Request failed (${response.status})`;
	} catch {
		return `Request failed (${response.status})`;
	}
}

/** Best-effort server-side cancel: stops ffmpeg and drops the temp file. */
export async function cancelSplitAudio(exportId: string): Promise<void> {
	const response = await fetch(`${API_BASE_URL}/split-audio/${exportId}/cancel`, {
		method: 'POST'
	});

	if (!response.ok && response.status !== 404 && response.status !== 409) {
		throw new ApiError(await parseError(response), { status: response.status });
	}
}

export function splitAudioDownloadUrl(exportId: string): string {
	return `${API_BASE_URL}/split-audio/${exportId}/file`;
}
