/**
 * Shared WebVTT parsing -- powers the subtitle search panel and its
 * click/tap-to-seek, regardless of whether the track came from the Groq job
 * or an existing source caption.
 */

import type { SubtitleSegment } from '$lib/types';

const VTT_TIME = /(\d{2}):(\d{2}):(\d{2})[.,](\d{3})/;
const CUE_LINE = /-->/;
// WebVTT inline tags (karaoke-style timestamps, <c>/<v>/<b>/<i>/<u> styling)
// -- YouTube's auto-generated captions use these for word-by-word highlighting;
// they're meant for the renderer, not to be displayed as literal text.
const VTT_TAG = /<[^>]*>/g;

function parseTimestamp(raw: string): number {
	const match = VTT_TIME.exec(raw);

	if (!match) {return 0;}

	const [, hh, mm, ss, ms] = match;

	return Number(hh) * 3600 + Number(mm) * 60 + Number(ss) + Number(ms) / 1000;
}

/** Parses WebVTT (and SRT, which differs only in the comma/period decimal
 *  separator and numeric cue-index lines this already skips over). */
export function parseVtt(text: string): SubtitleSegment[] {
	const segments: SubtitleSegment[] = [];
	const lines = text.replace(/\r\n/g, '\n').split('\n');

	for (let i = 0; i < lines.length; i++) {
		if (!CUE_LINE.test(lines[i])) {continue;}

		const [startRaw, endRaw] = lines[i].split('-->');
		const start = parseTimestamp(startRaw);
		const end = parseTimestamp(endRaw);

		const textLines: string[] = [];
		let j = i + 1;

		while (j < lines.length && lines[j].trim() !== '') {
			textLines.push(lines[j].trim());
			j++;
		}

		const cueText = textLines
			.join(' ')
			.replace(VTT_TAG, '')
			.replace(/\s+/g, ' ')
			.trim();

		if (cueText) {segments.push({ start, end, text: cueText });}

		i = j;
	}

	return segments;
}

export async function fetchAndParseVtt(url: string): Promise<SubtitleSegment[]> {
	const response = await fetch(url);

	if (!response.ok) {throw new Error(`Failed to fetch subtitle track (${response.status})`);}

	return parseVtt(await response.text());
}

function formatVttTime(seconds: number): string {
	const ms = Math.max(0, Math.round(seconds * 1000));
	const hh = Math.floor(ms / 3_600_000);
	const mm = Math.floor((ms % 3_600_000) / 60_000);
	const ss = Math.floor((ms % 60_000) / 1000);
	const mmm = ms % 1000;

	return `${String(hh).padStart(2, '0')}:${String(mm).padStart(2, '0')}:${String(ss).padStart(2, '0')}.${String(mmm).padStart(3, '0')}`;
}

/** Serialize parsed segments back to WebVTT and wrap it in a blob URL.
 *
 *  Native `<track src>` rendering needs a URL, but the URLs a track arrives
 *  with are unreliable: a source caption URL can expire or fail CORS, and a
 *  generated track's server URL dies with the job's TTL. The segments
 *  themselves are always at hand (they're what the panel renders and what
 *  gets persisted), so a same-origin blob built from them is the one URL
 *  that always works. */
export function segmentsToVttUrl(segments: SubtitleSegment[]): string {
	const lines: string[] = ['WEBVTT', ''];

	for (const seg of segments) {
		lines.push(`${formatVttTime(seg.start)} --> ${formatVttTime(seg.end)}`);
		lines.push(seg.text);
		lines.push('');
	}

	return URL.createObjectURL(new Blob([lines.join('\n')], { type: 'text/vtt' }));
}
