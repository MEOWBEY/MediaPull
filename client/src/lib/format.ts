/** Small display formatters shared across components. Pure, UI-agnostic. */

/** Bytes → "12.3 MB", or "Unknown" when size is missing/zero. */
export function formatBytesToMB(bytes: number): string {
	if (!bytes || bytes <= 0) {
		return 'Unknown';
	}

	return `${Math.round((bytes / (1024 * 1024)) * 10) / 10} MB`;
}

/** Seconds → "m:ss". */
export function formatSecondsToTime(seconds: number): string {
	if (!seconds) {
		return '0:00';
	}

	const mins = Math.floor(seconds / 60);
	const secs = Math.floor(seconds % 60)
		.toString()
		.padStart(2, '0');

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
