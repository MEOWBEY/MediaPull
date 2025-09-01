import { browser } from '$app/environment';

export interface VideoFormats {
	proxiedVideoUrl: string;
	ext: string;
	format_id: string;
	sourceVideoUrl: string;
	protocol: string;
	resolution: string | number;
	tbr: number;
	filesize?: number;
}

export interface VideoMetadata {
	aspect_ratio: string;
	duration: number;
	height: number;
	id: string;
	thumbnail: string;
	title: string;
	upload_date: string;
	webpage_url: string;
	width: number;
}

export interface VideoExtractResults {
	formats: VideoFormats[];
	metadata: VideoMetadata;
}

export interface GroupedVideo {
	title: string;
	thumbnail: string;
	duration: number;
	type: string;
	qualities: VideoFormats[];
	height: number;
	width: number;
	id: string;
	upload_date: string;
	aspect_ratio: string;
	webpage_url: string;
}

export interface OvcProxyResults {
	id: string;
	proxiedVideoUrl: string;
	sourceVideoUrl: string;
	ovcVideoUrl: string;
}

function determineMediaType(format) {
	const ext = (format?.ext ?? '').toLowerCase();
	const protocol = (format?.protocol ?? '').toLowerCase();

	if (protocol === 'm3u8_native') return 'application/x-mpegURL';
	if (protocol === 'dash') return 'application/dash+xml';

	const audioTypes: Record<string, string> = {
		mp3: 'audio/mpeg',
		aac: 'audio/aac',
		ogg: 'audio/ogg',
		wav: 'audio/wav',
		flac: 'audio/flac',
		m4a: 'audio/mp4',
		opus: 'audio/opus'
	};

	const videoTypes: Record<string, string> = {
		mp4: 'video/mp4',
		webm: 'video/webm',
		mkv: 'video/x-matroska',
		mov: 'video/quicktime',
		avi: 'video/x-msvideo'
	};

	return audioTypes[ext] || videoTypes[ext] || 'video/mp4';
}

function groupVideosByQuality(
	videos: Array<{
		formats?;
		metadata?;
	}> = []
) {
	const results = [];

	videos.forEach((item, i) => {
		const formats = item.formats?.filter(Boolean) ?? [];
		if (!formats.length) return;

		const metadata = item.metadata ?? {};
		const hasValidTitle = metadata.title && metadata.title !== 'unknown';

		// Group formats by media type (or create individual entries if no valid title)
		const formatsByType = {};

		if (hasValidTitle) {
			formats.forEach((format) => {
				const mediaType = determineMediaType(format);
				(formatsByType[mediaType] ??= []).push(format);
			});
		} else {
			// Create separate entry for each format when no valid title
			formats.forEach((format, idx) => {
				formatsByType[`${determineMediaType(format)}-${idx}`] = [format];
			});
		}

		// Create grouped video for each media type/format
		Object.entries(formatsByType).forEach(([typeKey, formatList]) => {
			const qualities = formatList
				.map((format) => {
					const durationSec = Number(metadata.duration) || 0;
					const tbr = Number(format.tbr) || 0;
					const filesize =
						Number(format.filesize) ||
						(durationSec && tbr ? Math.round(tbr * durationSec * 125) : 0);

					return {
						proxiedVideoUrl: format.proxiedVideoUrl ?? '',
						sourceVideoUrl: format.sourceVideoUrl ?? '',
						ext: format.ext ?? '',
						tbr,
						filesize,
						protocol: format.protocol ?? '',
						format_id: format.format_id ?? '',
						resolution: Number(format.resolution) || 0
					};
				})
				.filter(Boolean)
				.sort((a, b) => b.resolution - a.resolution);

			results.push({
				title: hasValidTitle ? metadata.title : undefined,
				thumbnail: metadata.thumbnail,
				duration: Number(metadata.duration) || undefined,
				type: determineMediaType(formatList[0]),
				qualities,
				height: metadata.height,
				width: metadata.width,
				id: metadata.id,
				upload_date: metadata.upload_date,
				aspect_ratio: metadata.aspect_ratio,
				webpage_url: metadata.webpage_url
			});
		});
	});

	return results;
}

function sortResults(results, preferences) {
	if (!results) return null;

	return [...results].sort((a, b) => {
		let comparison = 0;

		switch (preferences.videoSortField) {
			case 'name':
				comparison = (a.filename ?? '').localeCompare(b.filename ?? '');
				break;
			case 'size':
				comparison = parseInt(a.fileSize ?? '0', 10) - parseInt(b.fileSize ?? '0', 10);
				break;
			case 'quality':
				comparison =
					parseInt(a.quality?.replace(/\D/g, '') ?? '0', 10) -
					parseInt(b.quality?.replace(/\D/g, '') ?? '0', 10);
				break;
		}

		return preferences.videoSortOrder === 'desc' ? -comparison : comparison;
	});
}

class AppStore {
	isOVCProxyRunning = $state(false);
	isVideoExtractRunning = $state(false);

	ovcProxyResults = $state([]);
	videoExtractResults = $state([]);

	ovcProxyError = $state<string | null>(null);
	videoExtractError = $state<string | null>(null);

	preferences = $state({
		theme: 'system' as 'light' | 'dark' | 'system',
		layoutList: 'grid' as 'grid' | 'list',
		videoSortField: 'quality' as 'name' | 'size' | 'quality',
		videoSortOrder: 'desc' as 'asc' | 'desc',
		enableAnimations: true,
		enableCompact: false,
		enableHighContrast: false,
		enableProxyForVideoExtract: true,
		enableVideoMute: true,
		enableVideoPreloadMetadata: false,
		showVideoThumbnail: true,
		showHlsTypeDownloadButton: false
	});

	constructor() {
		if (browser) {
			this.loadData();
		}
	}

	getOvcProxyResultsFromStore() {
		return sortResults(this.ovcProxyResults, this.preferences);
	}

	getVideoExtractResultsFromStore() {
		return sortResults(this.videoExtractResults, this.preferences);
	}

	addOvcProxyResultsToStore(data): void {
		this.ovcProxyResults.push(data);

		if (this.ovcProxyResults.length > 50) {
			this.ovcProxyResults.splice(50);
		}

		this.saveData('ovcProxyResults', this.ovcProxyResults);
	}

	addVideoExtractResultsToStore(data): void {
		const grouped = groupVideosByQuality([data]);
		this.videoExtractResults.push(...grouped);

		if (this.videoExtractResults.length > 50) {
			this.videoExtractResults.splice(50);
		}

		this.saveData('videoExtractResults', this.videoExtractResults);
	}

	clearOvcProxyResultsFromStore(): void {
		this.ovcProxyResults = [];
		this.removeData('ovcProxyResults');
	}

	clearVideoExtractResultsFromStore(): void {
		this.videoExtractResults = [];
		this.removeData('videoExtractResults');
	}

	updatePreferences(updates: Partial<typeof this.preferences>): void {
		Object.assign(this.preferences, updates);
		this.saveData('preferences', this.preferences);
	}

	clearErrors(): void {
		this.ovcProxyError = null;
		this.videoExtractError = null;
	}

	reset(): void {
		this.ovcProxyResults = [];
		this.videoExtractResults = [];
		this.ovcProxyError = null;
		this.videoExtractError = null;
		this.clearStorage();
	}

	getStats() {
		if (!browser) return { size: 0, hitRate: 0, totalAccess: 0 };

		let totalItems = 0;
		let totalAccess = 0;

		['ovcProxyResults', 'videoExtractResults', 'preferences'].forEach((key) => {
			const item = localStorage.getItem(key);
			if (item) {
				totalItems++;
				totalAccess++;
			}
		});

		return {
			size: totalItems,
			hitRate: totalAccess > 0 ? (totalItems / totalAccess) * 100 : 0,
			totalAccess
		};
	}

	private loadData(): void {
		try {
			const proxyData = localStorage.getItem('ovcProxyResults');
			if (proxyData) this.ovcProxyResults = JSON.parse(proxyData);

			const extractData = localStorage.getItem('videoExtractResults');
			if (extractData) this.videoExtractResults = JSON.parse(extractData);

			const preferencesData = localStorage.getItem('preferences');
			if (preferencesData) Object.assign(this.preferences, JSON.parse(preferencesData));
		} catch (error) {
			console.warn('Failed to load data from localStorage:', error);
		}
	}

	private saveData(key: string, data: unknown): void {
		if (!browser) return;

		try {
			if (data !== null && data !== undefined) {
				localStorage.setItem(key, JSON.stringify(data));
			} else {
				localStorage.removeItem(key);
			}
		} catch (error) {
			console.warn(`Failed to save ${key} to localStorage:`, error);
		}
	}

	private removeData(key: string): void {
		if (!browser) return;
		localStorage.removeItem(key);
	}

	private clearStorage(): void {
		if (!browser) return;

		['ovcProxyResults', 'videoExtractResults', 'preferences'].forEach((key) => {
			localStorage.removeItem(key);
		});
	}
}

export const appStore = new AppStore();
