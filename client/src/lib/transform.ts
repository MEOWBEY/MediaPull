/** Pure transforms: raw API video -> grouped, normalized client model. */

import { isAudioType } from '$lib/format';
import { buildProxiedUrl } from '$lib/proxy-url';
import type {
	FormatGroup,
	GroupedGallery,
	GroupedVideo,
	IncomingFormat,
	IncomingGallery,
	IncomingGalleryImage,
	ImageAsset,
	IncomingVideo,
	MediaType,
	SubtitleTrack,
	VideoFormat
} from '$lib/types';

// Tab order when a source has several format kinds: progressive video first
// (the most immediately playable), then adaptive streaming, audio last.
const KIND_PRIORITY: Record<string, number> = {
	'application/x-mpegURL': 1,
	'application/dash+xml': 2
};

function kindPriority(type: MediaType): number {
	if (isAudioType(type)) {
		return 3;
	}

	return KIND_PRIORITY[type] ?? 0;
}

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

	if (protocol === 'm3u8_native') {
		return 'application/x-mpegURL';
	}
	if (protocol === 'dash') {
		return 'application/dash+xml';
	}

	return AUDIO_TYPES[ext] ?? VIDEO_TYPES[ext] ?? 'video/mp4';
}

function normalizeFormat(format: IncomingFormat, durationSec: number): VideoFormat {
	const tbr = Number(format.tbr) || 0;
	const filesize =
		Number(format.filesize) || (durationSec && tbr ? Math.round(tbr * durationSec * 125) : 0);

	return {
		sourceVideoUrl: format.sourceVideoUrl ?? '',
		proxiedVideoUrl: buildProxiedUrl(
			format.sourceVideoUrl,
			format.httpHeaders,
			format.protocol,
			format.cookieToken
		),
		ext: format.ext ?? '',
		tbr,
		filesize,
		protocol: format.protocol ?? '',
		format_id: format.format_id ?? '',
		resolution: Number(format.resolution) || 0,
		videoOnly: Boolean(format.videoOnly)
	};
}

/** Existing-caption URLs come straight from the source (e.g. YouTube's
 *  timedtext endpoint) with no proxying. Both the native `<track src>` and
 *  our own fetch-for-the-panel need to load that cross-origin, and it isn't
 *  reliably CORS-safe (signed/expiring URLs, referer checks) -- route it
 *  through the same proxy the video/audio URLs already use so it behaves the
 *  same regardless of source. */
function proxiedSubtitleTracks(tracks: SubtitleTrack[] | undefined): SubtitleTrack[] {
	return (tracks ?? []).map((track) => ({
		...track,
		url: buildProxiedUrl(track.url, null, 'https') || track.url
	}));
}

/** Group an incoming video's formats by media type into renderable cards. A
 *  video whose formats span several kinds (progressive + HLS + a separate
 *  audio-only stream, ...) becomes ONE card with several `formatGroups` --
 *  the player renders these as tabs, since they're all the same source and
 *  share one subtitle track. Formats that can't be tied to a real title are
 *  probably unrelated stray content, so each stays its own single-group card. */
export function groupVideosByQuality(videos: IncomingVideo[] = []): GroupedVideo[] {
	const results: GroupedVideo[] = [];

	for (const item of videos) {
		const formats = (item.formats ?? []).filter(Boolean);

		if (!formats.length) {
			continue;
		}

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

		const formatGroups: FormatGroup[] = Object.values(buckets)
			.map((bucket) => ({
				type: determineMediaType(bucket[0]),
				qualities: bucket
					.map((format) => normalizeFormat(format, durationSec))
					.sort((a, b) => b.resolution - a.resolution)
			}))
			.sort((a, b) => kindPriority(a.type) - kindPriority(b.type));

		if (hasValidTitle) {
			results.push({
				id: metadata.id,
				title: metadata.title,
				thumbnail: metadata.thumbnail,
				duration: durationSec || undefined,
				formatGroups,
				height: metadata.height,
				width: metadata.width,
				upload_date: metadata.upload_date,
				aspect_ratio: metadata.aspect_ratio,
				webpage_url: metadata.webpage_url,
				subtitleTracks: proxiedSubtitleTracks(item.subtitleTracks)
			});
		} else {
			for (const group of formatGroups) {
				results.push({
					id: metadata.id,
					thumbnail: metadata.thumbnail,
					duration: durationSec || undefined,
					formatGroups: [group],
					height: metadata.height,
					width: metadata.width,
					upload_date: metadata.upload_date,
					aspect_ratio: metadata.aspect_ratio,
					webpage_url: metadata.webpage_url,
					subtitleTracks: proxiedSubtitleTracks(item.subtitleTracks)
				});
			}
		}
	}

	return results;
}

function normalizeImage(image: IncomingGalleryImage): ImageAsset {
	const sourceUrl = image.url ?? '';

	return {
		url: buildProxiedUrl(sourceUrl, image.httpHeaders, 'https', image.cookieToken) || sourceUrl,
		sourceUrl,
		width: Number(image.width) || 0,
		height: Number(image.height) || 0,
		filesize: Number(image.filesize) || 0,
		ext: image.ext ?? 'jpg'
	};
}

/** Group incoming gallery images by source page -- much simpler than video's
 *  format-group tabs, since images have no "kind" to bucket by. One
 *  `IncomingGallery` (already one source page) becomes one `GroupedGallery`. */
export function groupGalleriesBySource(galleries: IncomingGallery[] = []): GroupedGallery[] {
	const results: GroupedGallery[] = [];

	for (const item of galleries) {
		const images = (item.images ?? []).filter((img) => img?.url);

		if (!images.length) {
			continue;
		}

		results.push({
			title: item.title,
			webpage_url: item.webpageUrl,
			images: images.map(normalizeImage),
			skippedCount: item.skippedCount || undefined,
			warnings: item.warnings?.length ? item.warnings : undefined
		});
	}

	return results;
}

/** Every quality across every format-group tab of a card. */
export function allQualities(item: GroupedVideo): VideoFormat[] {
	return (item.formatGroups ?? []).flatMap((g) => g.qualities);
}

export function maxResolution(item: GroupedVideo): number {
	return allQualities(item).reduce((max, q) => Math.max(max, Number(q.resolution) || 0), 0);
}

export function maxFilesize(item: GroupedVideo): number {
	return allQualities(item).reduce((max, q) => Math.max(max, Number(q.filesize) || 0), 0);
}
