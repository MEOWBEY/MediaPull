/** Small display formatters shared across components. Pure, UI-agnostic. */

/** Bytes → "12.3 MB", or "Unknown" when size is missing/zero. */
export function formatBytesToMB(bytes: number): string {
	if (!bytes || bytes <= 0) {
		return 'Unknown';
	}

	return `${Math.round((bytes / (1024 * 1024)) * 10) / 10} MB`;
}

/** Seconds → "m:ss", or "h:mm:ss" from one hour up. */
export function formatSecondsToTime(seconds: number): string {
	if (!seconds || seconds < 0) {
		return '0:00';
	}

	const total = Math.floor(seconds);
	const hours = Math.floor(total / 3600);
	const mins = Math.floor((total % 3600) / 60);
	const secs = (total % 60).toString().padStart(2, '0');

	if (hours > 0) {
		return `${hours}:${mins.toString().padStart(2, '0')}:${secs}`;
	}

	return `${mins}:${secs}`;
}

/** yt-dlp "YYYYMMDD" → locale date string, or "" when malformed. */
export function formatYYYYMMDDToDate(yyyyMMdd: string): string {
	if (!yyyyMMdd || yyyyMMdd.length < 8) {
		return '';
	}

	const y = parseInt(yyyyMMdd.substring(0, 4), 10);
	const m = parseInt(yyyyMMdd.substring(4, 6), 10) - 1;
	const d = parseInt(yyyyMMdd.substring(6, 8), 10);

	return new Date(y, m, d).toLocaleDateString();
}

export function isAudioType(type: string): boolean {
	return typeof type === 'string' && type.startsWith('audio/');
}

/** Hostname minus a leading "www." -- shared by the video and gallery result
 *  lists for their export-filename and empty-title fallbacks. */
export function sourceHost(url: string | undefined): string {
	try {
		return new URL(url ?? '').hostname.replace(/^www\./, '');
	} catch {
		return '';
	}
}

// Friendly, organized labels: streaming protocols, then audio "<codec> Audio",
// then video "<container> Video". Falls back to the raw subtype. Shared by
// the extract-list card meta row and the player's format-kind tab strip.
const AUDIO_LABELS: Record<string, string> = {
	'audio/mpeg': 'MP3',
	'audio/aac': 'AAC',
	'audio/ogg': 'OGG',
	'audio/wav': 'WAV',
	'audio/flac': 'FLAC',
	'audio/mp4': 'M4A',
	'audio/opus': 'Opus'
};
const VIDEO_LABELS: Record<string, string> = {
	'video/mp4': 'MP4',
	'video/webm': 'WebM',
	'video/x-matroska': 'MKV',
	'video/quicktime': 'MOV',
	'video/x-msvideo': 'AVI'
};

/** Short label for one quality option in a format picker (e.g. "1080p", "MP3",
 *  falling back to "Source N" when a format has neither resolution nor ext). */
export function qualityLabel(
	q: { resolution?: number; ext?: string } | undefined,
	index: number
): string {
	if (q?.resolution) {
		return `${q.resolution}p`;
	}
	if (q?.ext) {
		return q.ext.toUpperCase();
	}

	return `Source ${index + 1}`;
}

/** Short human label for a media-kind (e.g. "HLS", "MP4 Video", "AAC Audio"). */
export function mediaKindLabel(type: string, audioWord: string): string {
	if (type === 'application/x-mpegURL') {
		return 'HLS';
	}
	if (type === 'application/dash+xml') {
		return 'DASH';
	}
	if (AUDIO_LABELS[type]) {
		return `${AUDIO_LABELS[type]} ${audioWord}`;
	}
	if (VIDEO_LABELS[type]) {
		return `${VIDEO_LABELS[type]} Video`;
	}
	if (isAudioType(type)) {
		return `${type.split('/')[1]?.toUpperCase()} ${audioWord}`;
	}

	return type.split('/')[1]?.toUpperCase() ?? type;
}
