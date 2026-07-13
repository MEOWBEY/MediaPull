/** Pure helpers for copying/exporting extracted links as text / .m3u playlists. */

import { allQualities } from '$lib/transform';
import type { GroupedVideo } from '$lib/types';

/** Resolves whether a given card should use its proxied URL (per-card setting). */
export type ProxyResolver = (video: GroupedVideo) => boolean;

/** Best URL for one quality, honoring the proxy preference. */
function qualityUrl(
	q: { proxiedVideoUrl?: string; sourceVideoUrl?: string },
	useProxy: boolean
): string {
	return useProxy
		? q.proxiedVideoUrl || q.sourceVideoUrl || ''
		: q.sourceVideoUrl || q.proxiedVideoUrl || '';
}

/** Every quality URL of one card, across all its format-group tabs (empty ones dropped). */
export function qualityLinks(video: GroupedVideo, useProxy: boolean): string[] {
	return allQualities(video).map((q) => qualityUrl(q, useProxy)).filter(Boolean);
}

/** Every quality URL across many cards. */
export function allQualityLinks(videos: GroupedVideo[], useProxyFor: ProxyResolver): string[] {
	return videos.flatMap((v) => qualityLinks(v, useProxyFor(v)));
}

/** Extended M3U playlist — one #EXTINF entry per quality, across the given cards. */
export function buildVideosM3u(videos: GroupedVideo[], useProxyFor: ProxyResolver): string {
	const lines = ['#EXTM3U'];

	for (const v of videos) {
		const useProxy = useProxyFor(v);
		const dur = Math.round(Number(v.duration) || 0) || -1;
		const base = (v.title || 'Untitled').replace(/[\r\n]+/g, ' ').trim();

		for (const q of allQualities(v)) {
			const url = qualityUrl(q, useProxy);

			if (!url) {continue;}

			const label = q.resolution ? `${q.resolution}p` : (q.ext || '').toUpperCase();

			lines.push(`#EXTINF:${dur},${base}${label ? ` (${label})` : ''}`);
			lines.push(url);
		}
	}

	return lines.join('\n');
}

/** Filesystem-safe slug from a title (for download filenames). */
export function safeFilename(title: string | undefined, fallback = 'pullbox'): string {
	const slug = (title ?? '')
		.replace(/[\\/:*?"<>|]+/g, '')
		.trim()
		.slice(0, 80);

	return slug || fallback;
}

/** Trigger a client-side download of a text blob. */
export function downloadTextFile(filename: string, content: string, mime = 'text/plain'): void {
	const blob = new Blob([content], { type: `${mime};charset=utf-8` });
	const url = URL.createObjectURL(blob);
	const a = document.createElement('a');

	a.href = url;
	a.download = filename;
	a.click();
	URL.revokeObjectURL(url);
}
