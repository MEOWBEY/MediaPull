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
