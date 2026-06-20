/** Pure transforms: raw API video -> grouped, normalized client model. */

import { buildProxiedUrl } from '$lib/proxy-url';
import type { GroupedVideo, IncomingFormat, IncomingVideo, MediaType, VideoFormat } from '$lib/types';

const AUDIO_TYPES: Record<string, MediaType> = {
	mp3: 'audio/mpeg',
	aac: 'audio/aac',
	ogg: 'audio/ogg',
	wav: 'audio/wav',
	flac: 'audio/flac',
	m4a: 'audio/mp4',
	opus: 'audio/opus'
};

const VIDEO_TYPES: Record<string, MediaType> = {
	mp4: 'video/mp4',
	webm: 'video/webm',
	mkv: 'video/x-matroska',
	mov: 'video/quicktime',
	avi: 'video/x-msvideo'
};

export function determineMediaType(format: IncomingFormat | undefined): MediaType {
	const ext = (format?.ext ?? '').toLowerCase();
	const protocol = (format?.protocol ?? '').toLowerCase();

	if (protocol === 'm3u8_native') {return 'application/x-mpegURL';}
	if (protocol === 'dash') {return 'application/dash+xml';}

	return AUDIO_TYPES[ext] ?? VIDEO_TYPES[ext] ?? 'video/mp4';
}

function normalizeFormat(format: IncomingFormat, durationSec: number): VideoFormat {
	const tbr = Number(format.tbr) || 0;
	const filesize =
		Number(format.filesize) || (durationSec && tbr ? Math.round(tbr * durationSec * 125) : 0);

	return {
		sourceVideoUrl: format.sourceVideoUrl ?? '',
		proxiedVideoUrl: buildProxiedUrl(format.sourceVideoUrl, format.httpHeaders, format.protocol),
		ext: format.ext ?? '',
		tbr,
		filesize,
		protocol: format.protocol ?? '',
		format_id: format.format_id ?? '',
		resolution: Number(format.resolution) || 0,
		videoOnly: Boolean(format.videoOnly)
	};
}

/** Group an incoming video's formats by media type into renderable cards. */
export function groupVideosByQuality(videos: IncomingVideo[] = []): GroupedVideo[] {
	const results: GroupedVideo[] = [];

	for (const item of videos) {
		const formats = (item.formats ?? []).filter(Boolean);

		if (!formats.length) {continue;}

		const metadata = item.metadata ?? {};
		const hasValidTitle = Boolean(metadata.title && metadata.title !== 'unknown');
		const durationSec = Number(metadata.duration) || 0;

		const buckets: Record<string, IncomingFormat[]> = {};

		if (hasValidTitle) {
			for (const format of formats) {
				const type = determineMediaType(format);

				(buckets[type] ??= []).push(format);
			}
		} else {
			formats.forEach((format, idx) => {
				buckets[`${determineMediaType(format)}-${idx}`] = [format];
			});
		}

		for (const bucket of Object.values(buckets)) {
			const qualities = bucket
				.map((format) => normalizeFormat(format, durationSec))
				.sort((a, b) => b.resolution - a.resolution);

			results.push({
				id: metadata.id,
				title: hasValidTitle ? metadata.title : undefined,
				thumbnail: metadata.thumbnail,
				duration: durationSec || undefined,
				type: determineMediaType(bucket[0]),
				qualities,
				height: metadata.height,
				width: metadata.width,
				upload_date: metadata.upload_date,
				aspect_ratio: metadata.aspect_ratio,
				webpage_url: metadata.webpage_url
			});
		}
	}

	return results;
}

export function maxResolution(item: GroupedVideo): number {
	return (item.qualities ?? []).reduce((max, q) => Math.max(max, Number(q.resolution) || 0), 0);
}

export function maxFilesize(item: GroupedVideo): number {
	return (item.qualities ?? []).reduce((max, q) => Math.max(max, Number(q.filesize) || 0), 0);
}
