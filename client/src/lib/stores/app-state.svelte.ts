import { browser } from '$app/environment';

// ============================================================================
// ESSENTIAL TYPE DEFINITIONS
// ============================================================================
export interface VideoFormat {
	id?: string;
	format_id?: string;
	title?: string;
	originalUrl?: string;
	downloadUrl: string;
	filename?: string;
	ext?: string;
	quality?: string;
	resolution?: string | number;
	height?: number;
	width?: number;
	fileSize?: string;
	filesize?: number;
	thumbnail?: string;
	duration?: number;
	protocol?: string;
	bitrate?: number;
	tbr?: number;
	fps?: number;
	codec?: string;
	container?: string;
	aspectRatio?: string;
}
export interface VideoMetadata {
	id?: string;
	title?: string;
	duration?: number;
	width?: number;
	height?: number;
	thumbnail?: string;
	upload_date?: string;
	webpage_url?: string;
	aspect_ratio?: string;
	tags?: string[];
	category?: string;
	language?: string;
}

export interface VideoQuality {
	src: string;
	downloadUrl: string;
	originalUrl: string;
	ext: string;
	tbr: number;
	filesize: number;
	protocol: string;
	format_id: string;
	resolution: number;
}

export interface OrganizedVideo {
	key: string;
	title?: string;
	sourceUrl: string;
	thumbnail?: string;
	duration?: number;
	type: string;
	qualities: VideoQuality[];
	height?: number;
	width?: number;
	id?: string;
	upload_date?: string;
	aspect_ratio?: string;
}

export interface PuppeteerProxiedUrlVideo extends VideoFormat {
	downloadUrl: string;
	id: string;
	status: 'puppeteerProxyingUrl' | 'completed' | 'failed';
	progress?: number;
	errorMessage?: string;
}

export interface ExtractedVideoData {
	id: string;
	title: string;
	description?: string;
	duration?: number;
	thumbnail?: string;
	uploader?: string;
	upload_date?: string;
	viewCount?: number;
	formats: VideoFormat[];
	totalFormats: number;
	sourceUrl: string;
	extractedAt: number;
	height?: number;
	width?: number;
	aspect_ratio?: string;
	metadata?: VideoMetadata;
}

export interface CacheEntry<T = unknown> {
	data: T;
	timestamp: number;
	expiresAt: number;
	accessCount: number;
	lastAccessed: number;
}

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

function generateId(): string {
	return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}

function isExpired(entry: CacheEntry): boolean {
	return Date.now() > entry.expiresAt;
}

function createReactiveSet<T>(): {
	value: Set<T>;
	add: (item: T) => void;
	delete: (item: T) => boolean;
	clear: () => void;
	has: (item: T) => boolean;
	size: number;
	forEach: (callback: (value: T) => void) => void;
} {
	let internalSet = $state(new Set<T>());

	return {
		get value() {
			return internalSet;
		},
		get size() {
			return internalSet.size;
		},
		add: (item: T) => {
			internalSet.add(item);
			internalSet = new Set(internalSet);
		},
		delete: (item: T) => {
			const deleted = internalSet.delete(item);
			if (deleted) internalSet = new Set(internalSet);
			return deleted;
		},
		clear: () => {
			internalSet.clear();
			internalSet = new Set(internalSet);
		},
		has: (item: T) => internalSet.has(item),
		forEach: (callback: (value: T) => void) => internalSet.forEach(callback)
	};
}

// ============================================================================
// SIMPLIFIED CACHE MANAGER
// ============================================================================

class SmartApiCache {
	private cache = $state<Map<string, CacheEntry>>(new Map());
	private readonly defaultTTL = 10 * 60 * 1000; // 10 minutes
	private readonly maxEntries = 100;
	private cleanupInterval?: NodeJS.Timeout;
	private persistenceKey = 'directlinker_smart_cache_v2';

	constructor() {
		if (browser) {
			this.initializeCache();
			this.startCleanupScheduler();
		}
	}

	private initializeCache(): void {
		this.loadFromStorage();

		window.addEventListener('storage', (e) => {
			if (e.key === this.persistenceKey) {
				this.loadFromStorage();
			}
		});
	}

	private startCleanupScheduler(): void {
		this.cleanupInterval = setInterval(
			() => {
				this.cleanup();
			},
			2 * 60 * 1000
		);
	}

	get<T>(key: string): T | null {
		const entry = this.cache.get(key);
		if (!entry || isExpired(entry)) {
			this.cache.delete(key);
			this.saveToStorage();
			return null;
		}

		entry.accessCount++;
		entry.lastAccessed = Date.now();
		this.cache.set(key, entry);

		return entry.data as T;
	}

	set<T>(key: string, data: T, ttl: number = this.defaultTTL): void {
		if (this.cache.size >= this.maxEntries) {
			this.evictLeastRecentlyUsed();
		}

		const entry: CacheEntry<T> = {
			data,
			timestamp: Date.now(),
			expiresAt: Date.now() + ttl,
			accessCount: 1,
			lastAccessed: Date.now()
		};

		this.cache.set(key, entry);
		this.saveToStorage();
	}

	delete(key: string): boolean {
		const deleted = this.cache.delete(key);
		if (deleted) this.saveToStorage();
		return deleted;
	}

	clear(): void {
		this.cache.clear();
		this.saveToStorage();
	}

	has(key: string): boolean {
		const entry = this.cache.get(key);
		if (!entry || isExpired(entry)) {
			this.cache.delete(key);
			return false;
		}
		return true;
	}

	getStats(): { size: number; hitRate: number; totalAccess: number } {
		let totalAccess = 0;
		for (const entry of this.cache.values()) {
			totalAccess += entry.accessCount;
		}

		return {
			size: this.cache.size,
			hitRate: totalAccess > 0 ? (this.cache.size / totalAccess) * 100 : 0,
			totalAccess
		};
	}

	private evictLeastRecentlyUsed(): void {
		let oldestKey = '';
		let oldestTime = Date.now();

		for (const [key, entry] of this.cache.entries()) {
			if (entry.lastAccessed < oldestTime) {
				oldestTime = entry.lastAccessed;
				oldestKey = key;
			}
		}

		if (oldestKey) {
			this.cache.delete(oldestKey);
		}
	}

	private cleanup(): void {
		const now = Date.now();
		let hasExpired = false;

		for (const [key, entry] of this.cache.entries()) {
			if (now > entry.expiresAt) {
				this.cache.delete(key);
				hasExpired = true;
			}
		}

		if (hasExpired) {
			this.saveToStorage();
		}
	}

	private saveToStorage(): void {
		if (!browser) return;

		try {
			const serialized = JSON.stringify(Array.from(this.cache.entries()));
			localStorage.setItem(this.persistenceKey, serialized);
		} catch (error) {
			console.warn('Failed to save cache to localStorage:', error);
			this.evictLeastRecentlyUsed();
		}
	}

	private loadFromStorage(): void {
		if (!browser) return;

		try {
			const stored = localStorage.getItem(this.persistenceKey);
			if (stored) {
				const entries = JSON.parse(stored) as [string, CacheEntry][];
				const validEntries = entries.filter(([, entry]) => !isExpired(entry));
				this.cache = new Map(validEntries);
			}
		} catch (error) {
			console.warn('Failed to load cache from localStorage:', error);
			localStorage.removeItem(this.persistenceKey);
		}
	}

	destroy(): void {
		if (this.cleanupInterval) {
			clearInterval(this.cleanupInterval);
		}
	}
}

// ============================================================================
// SIMPLIFIED VIDEO STORE
// ============================================================================

class VideoDataStore {
	// Input state
	inputUrl = $state<string>('');

	// Operation states
	puppeteerProxyingUrl = $state<boolean>(false);
	extracting = $state<boolean>(false);
	puppeteerProxyUrlQueue = createReactiveSet<string>();

	// Data states
	puppeteerProxiedUrlVideos = $state<PuppeteerProxiedUrlVideo[]>([]);
	extractedData = $state<ExtractedVideoData | null>(null);

	// Error states
	puppeteerProxyUrlError = $state<string | null>(null);
	extractionError = $state<string | null>(null);

	// UI preferences
	preferences = $state({
		theme: 'system' as 'light' | 'dark' | 'system',
		viewMode: 'grid' as 'grid' | 'list',
		sortBy: 'quality' as 'name' | 'size' | 'quality',
		sortOrder: 'desc' as 'asc' | 'desc',
		showThumbnails: true,
		animationsEnabled: true,
		compactMode: false,
		muteByDefault: true,
		preloadMetadata: false,
		useProxy: true,
		showHlsDownloadButton: false,
		cacheEnabled: true,
		autoClearCache: false,
		highContrast: false,
		keyboardShortcuts: true
	});

	private readonly storageKeys = {
		puppeteerProxiedUrlVideos: 'directlinker_puppeteerProxiedUrl_videos_v2',
		extractedData: 'directlinker_extracted_data_v2',
		preferences: 'directlinker_preferences_v2',
		inputUrl: 'directlinker_input_url'
	};

	constructor() {
		if (browser) {
			this.loadPersistedData();
		}
	}

	private loadPersistedData(): void {
		try {
			const storedPuppeteerProxiedUrl = localStorage.getItem(
				this.storageKeys.puppeteerProxiedUrlVideos
			);
			if (storedPuppeteerProxiedUrl) {
				this.puppeteerProxiedUrlVideos = JSON.parse(storedPuppeteerProxiedUrl);
			}

			const storedExtracted = localStorage.getItem(this.storageKeys.extractedData);
			if (storedExtracted) {
				const parsed = JSON.parse(storedExtracted);
				const hourAgo = Date.now() - 60 * 60 * 1000;
				if (parsed.extractedAt > hourAgo) {
					this.extractedData = parsed;
				}
			}

			const storedPrefs = localStorage.getItem(this.storageKeys.preferences);
			if (storedPrefs) {
				Object.assign(this.preferences, JSON.parse(storedPrefs));
			}

			const storedUrl = localStorage.getItem(this.storageKeys.inputUrl);
			if (storedUrl) {
				this.inputUrl = storedUrl;
			}
		} catch (error) {
			console.warn('Failed to load persisted data:', error);
		}
	}

	reset(): void {
		this.puppeteerProxiedUrlVideos.length = 0;
		this.extractedData = null;
		this.puppeteerProxyUrlError = null;
		this.extractionError = null;
		this.puppeteerProxyUrlQueue.clear();
		this.clearPersistedData();
	}

	clearErrors(): void {
		this.puppeteerProxyUrlError = null;
		this.extractionError = null;
	}

	addPuppeteerProxiedUrlVideo(video: PuppeteerProxiedUrlVideo): void {
		video.status = 'completed';

		const existingIndex = this.puppeteerProxiedUrlVideos.findIndex((v) => v.id === video.id);
		if (existingIndex !== -1) {
			this.puppeteerProxiedUrlVideos[existingIndex] = video;
		} else {
			this.puppeteerProxiedUrlVideos.unshift(video);
		}

		if (this.puppeteerProxiedUrlVideos.length > 50) {
			this.puppeteerProxiedUrlVideos = this.puppeteerProxiedUrlVideos.slice(0, 50);
		}

		this.savePuppeteerProxiedUrlVideos();
	}

	setExtractedData(data: ExtractedVideoData): void {
		data.extractedAt = Date.now();
		data.id = generateId();
		this.extractedData = data;
		this.saveExtractedData();
	}

	clearExtractedData(): void {
		this.extractedData = null;
		if (browser) {
			localStorage.removeItem(this.storageKeys.extractedData);
			const cacheKey = `extract-${this.inputUrl.trim()}`;
			apiCache.delete(cacheKey);
		}
	}

	clearPuppeteerProxiedUrlVideos(): void {
		this.puppeteerProxiedUrlVideos.length = 0;
		if (browser) {
			localStorage.removeItem(this.storageKeys.puppeteerProxiedUrlVideos);
		}
	}

	updatePreferences(updates: Partial<typeof this.preferences>): void {
		Object.assign(this.preferences, updates);
		this.savePreferences();
	}

	updateInputUrl(url: string): void {
		this.inputUrl = url;
		this.saveInputUrl();
	}

	getSortedPuppeteerProxiedUrlVideos(): PuppeteerProxiedUrlVideo[] {
		const sorted = [...this.puppeteerProxiedUrlVideos];

		sorted.sort((a, b) => {
			let comparison = 0;

			switch (this.preferences.sortBy) {
				case 'name':
					comparison = (a.filename || '').localeCompare(b.filename || '');
					break;
				case 'size': {
					const aSize = parseInt(a.fileSize || '0');
					const bSize = parseInt(b.fileSize || '0');
					comparison = aSize - bSize;
					break;
				}
				case 'quality': {
					const aQuality = parseInt(a.quality?.replace(/\D/g, '') || '0');
					const bQuality = parseInt(b.quality?.replace(/\D/g, '') || '0');
					comparison = aQuality - bQuality;
					break;
				}
			}

			return this.preferences.sortOrder === 'desc' ? -comparison : comparison;
		});

		return sorted;
	}

	// Persistence methods
	private savePuppeteerProxiedUrlVideos(): void {
		if (!browser) return;
		try {
			localStorage.setItem(
				this.storageKeys.puppeteerProxiedUrlVideos,
				JSON.stringify(this.puppeteerProxiedUrlVideos)
			);
		} catch (error) {
			console.warn('Failed to save puppeteerProxiedUrl videos:', error);
		}
	}

	private saveExtractedData(): void {
		if (!browser) return;
		try {
			if (this.extractedData) {
				localStorage.setItem(this.storageKeys.extractedData, JSON.stringify(this.extractedData));
			} else {
				localStorage.removeItem(this.storageKeys.extractedData);
			}
		} catch (error) {
			console.warn('Failed to save extracted data:', error);
		}
	}

	private savePreferences(): void {
		if (!browser) return;
		try {
			localStorage.setItem(this.storageKeys.preferences, JSON.stringify(this.preferences));
		} catch (error) {
			console.warn('Failed to save preferences:', error);
		}
	}

	private saveInputUrl(): void {
		if (!browser) return;
		try {
			localStorage.setItem(this.storageKeys.inputUrl, this.inputUrl);
		} catch (error) {
			console.warn('Failed to save input URL:', error);
		}
	}

	private clearPersistedData(): void {
		if (!browser) return;
		Object.values(this.storageKeys).forEach((key) => {
			localStorage.removeItem(key);
		});
	}
}

// ============================================================================
// UI STATE MANAGER
// ============================================================================

class UIStateManager {
	loadingStates = $state<Map<string, boolean>>(new Map());

	setLoading(key: string, loading: boolean): void {
		if (loading) {
			this.loadingStates.set(key, true);
		} else {
			this.loadingStates.delete(key);
		}
	}
}

// ============================================================================
// STORE INSTANCES
// ============================================================================

export const videoStore = new VideoDataStore();
export const apiCache = new SmartApiCache();
export const uiState = new UIStateManager();

// ============================================================================
// MEDIA TYPE AND FORMAT HELPERS
// ============================================================================

function getMediaType(format: VideoFormat): string {
	const ext = (format.ext || '').toString().toLowerCase();
	const protocol = (format.protocol || '').toString().toLowerCase();

	// HLS detection
	if (protocol === 'm3u8_native') {
		return 'application/x-mpegURL';
	}

	// DASH detection
	if (protocol === 'dash') {
		return 'application/dash+xml';
	}

	// Audio formats
	if (ext === 'mp3') return 'audio/mpeg';
	if (ext === 'aac') return 'audio/aac';
	if (ext === 'ogg') return 'audio/ogg';
	if (ext === 'wav') return 'audio/wav';
	if (ext === 'flac') return 'audio/flac';
	if (ext === 'm4a') return 'audio/mp4';
	if (ext === 'opus') return 'audio/opus';

	// Video formats
	if (ext === 'mp4') return 'video/mp4';
	if (ext === 'webm') return 'video/webm';
	if (ext === 'mkv') return 'video/x-matroska';
	if (ext === 'mov') return 'video/quicktime';
	if (ext === 'avi') return 'video/x-msvideo';

	// Default fallback
	return 'video/mp4';
}

function createVideoQuality(format: VideoFormat, metadata: ExtractedVideoData): VideoQuality | null {
	const src = format.downloadUrl || format.originalUrl || '';
	if (!src) return null;

	const filesize =
		metadata?.duration && format.tbr
			? ((format.tbr * metadata.duration) / 8) * 1024
			: format.filesize || 0;

	return {
		src,
		downloadUrl: format.downloadUrl || '',
		originalUrl: format.originalUrl || '',
		ext: format.ext || '',
		tbr: format.tbr || 0,
		filesize,
		protocol: format.protocol || '',
		format_id: format.format_id || '',
		resolution: typeof format.resolution === 'string' ? 
			parseInt(format.resolution.replace(/\D/g, '')) || 0 : 
			format.resolution || 0
	};
}

function createOrganizedVideo(
	key: string, 
	title: string | undefined, 
	formats: VideoFormat[], 
	metadata: ExtractedVideoData
): OrganizedVideo {
	const qualities = formats
		.map((format) => createVideoQuality(format, metadata))
		.filter((q): q is VideoQuality => q !== null)
		.sort((a, b) => b.resolution - a.resolution);

	return {
		key,
		title,
		sourceUrl: formats[0]?.originalUrl || '',
		thumbnail: metadata?.thumbnail,
		duration: metadata?.duration,
		type: getMediaType(formats[0]),
		qualities,
		height: metadata?.height,
		width: metadata?.width,
		id: metadata?.id,
		upload_date: metadata?.upload_date,
		aspect_ratio: metadata?.aspect_ratio
	};
}

// ============================================================================
// MAIN ORGANIZATION FUNCTION
// ============================================================================

export function organizeVideoFormats(formats: VideoFormat[] = [], metadata: ExtractedVideoData): OrganizedVideo[] {
	if (!formats.length) return [];

	const validFormats = formats.filter(Boolean);
	const hasValidTitle = metadata?.title && metadata.title !== 'unknown';

	if (!hasValidTitle) {
		// Create separate entry for each format
		return validFormats.map((format, index) =>
			createOrganizedVideo(`format_${index}-${getMediaType(format)}`, undefined, [format], metadata)
		);
	}

	// Group formats by media type
	const groupedByType = validFormats.reduce((acc, format) => {
		const mediaType = getMediaType(format);
		if (!acc[mediaType]) acc[mediaType] = [];
		acc[mediaType].push(format);
		return acc;
	}, {} as Record<string, VideoFormat[]>);

	// Create organized videos for each media type
	return Object.entries(groupedByType).map(([mediaType, formatList]) =>
		createOrganizedVideo(`${metadata.title}-${mediaType}`, metadata.title, formatList, metadata)
	);
}

// ============================================================================
// CLEANUP
// ============================================================================

if (browser) {
	window.addEventListener('beforeunload', () => {
		apiCache.destroy();
	});
}