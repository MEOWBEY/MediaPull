import { browser } from '$app/environment';

// ============================================================================
// ESSENTIAL TYPE DEFINITIONS
// ============================================================================
export interface VideoFormat {
	id: string;
	title?: string;
	originalUrl: string;
	downloadUrl: string;
	filename?: string;
	extension?: string;
	quality?: string;
	resolution?: string;
	height?: number;
	width?: number;
	fileSize?: string;
	filesize?: string;
	thumbnail?: string;
	duration?: number;
	isHLS?: boolean;
	protocol?: 'http' | 'https' | 'hls' | 'dash';
	bitrate?: number;
	fps?: number;
	codec?: string;
	container?: string;
	aspectRatio?: string;
}

export type MediaType = 'video' | 'audio' | 'hls' | 'dash' | 'other';

export interface VideoQuality {
	src: string;
	label: string;
	resolution: string;
}

export interface OrganizedVideo {
	key: string;
	title: string;
	sourceUrl: string;
	thumbnail?: string;
	duration?: number;
	type: MediaType;
	qualities: VideoQuality[];
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
	uploadDate?: string;
	viewCount?: number;
	formats: VideoFormat[];
	totalFormats: number;
	sourceUrl: string;
	extractedAt: number;
	metadata?: {
		tags?: string[];
		category?: string;
		language?: string;
		subtitles?: Array<{ lang: string; url: string }>;
	};
}

export interface VideoGroup {
	groupKey: string;
	title: string;
	sourceUrl: string;
	types: Record<
		string,
		{
			type: 'video' | 'audio' | 'hls' | 'dash';
			formats: Record<string, VideoFormat>;
			bestQuality?: VideoFormat;
		}
	>;
	thumbnail?: string;
	duration?: number;
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

	// Fixed cache clearing methods
	clearExtractedData(): void {
		this.extractedData = null;
		if (browser) {
			localStorage.removeItem(this.storageKeys.extractedData);
			// Clear related cache entries
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
// HELPERS
// ============================================================================

function getHeight(format: any): number {
	if (format.height && Number.isFinite(format.height)) return format.height;

	if (typeof format.resolution === 'string') {
		const heightMatch = format.resolution.match(/(\d+)p/);
		if (heightMatch) return parseInt(heightMatch[1], 10);

		const dimensionMatch = format.resolution.match(/(\d+)x(\d+)/);
		if (dimensionMatch) return parseInt(dimensionMatch[2], 10);
	}

	return 0;
}

function getMediaType(format: any): string {
	const ext = (format.extension || '').toString().toLowerCase();
	const url = (format.originalUrl || format.downloadUrl || '').toLowerCase();

	// HLS detection
	if (format.isHLS || format.protocol === 'hls' || ext === 'm3u8' || url.includes('.m3u8')) {
		return 'application/x-mpegURL';
	}

	// DASH detection
	if (format.protocol === 'dash' || ext === 'mpd') {
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

function createGroupKey(format: any): string {
	const url = format.originalUrl || format.downloadUrl || '';
	if (!url) return format.id || 'unknown';

	try {
		const urlObj = new URL(url);
		const pathParts = urlObj.pathname.split('/').filter(Boolean);
		const filename = pathParts.pop() || '';
		const baseName = filename
			.replace(/\.[^/.]+$/, '')
			.replace(/(-\d{2,4}p$)|(-\d{2,4}x\d{2,4}$)/i, '');
		return `${urlObj.hostname}/${baseName}`;
	} catch {
		return format.id || 'unknown';
	}
}

function createQualityLabel(format: any): string {
	const height = getHeight(format);
	if (height > 0) return `${height}p`;
	if (format.resolution) return format.resolution;
	return format.extension?.toUpperCase() || 'Unknown';
}

// ============================================================================
// MAIN ORGANIZATION FUNCTION
// ============================================================================

export function organizeVideoFormats(formats: any[] = []): OrganizedVideo[] {
	if (!formats.length) return [];

	// Group formats by source and type
	const groups: Record<string, Record<MediaType, any[]>> = {};

	for (const format of formats) {
		if (!format) continue;

		const groupKey = createGroupKey(format);
		const mediaType = getMediaType(format);

		if (!groups[groupKey]) {
			groups[groupKey] = {} as Record<MediaType, any[]>;
		}
		if (!groups[groupKey][mediaType]) {
			groups[groupKey][mediaType] = [];
		}

		groups[groupKey][mediaType].push(format);
	}

	// Convert groups to organized videos
	const result: OrganizedVideo[] = [];

	for (const [groupKey, typeGroups] of Object.entries(groups)) {
		for (const [mediaType, formatList] of Object.entries(typeGroups) as [MediaType, any[]][]) {
			if (formatList.length === 0) continue;

			const firstFormat = formatList[0];

			// Create qualities array sorted by height (highest first)
			const qualities: VideoQuality[] = formatList
				.map((format) => ({
					src: format.downloadUrl || format.originalUrl || '',
					downloadUrl: format.downloadUrl || '',
					extension: format.extension || '',
					fileSize: format.fileSize || null,
					height: format.height || null,
					id: format.id || '',
					isHLS: format.isHLS || false,
					originalUrl: format.originalUrl || '',
					thumbnail: format.thumbnail || '',
					width: format.width || null,
					label: createQualityLabel(format),
					resolution: format.resolution || `${getHeight(format)}p`,
				}))
				.filter((q) => q.src) // Only include formats with valid URLs
				.sort((a, b) => (b.resolution || 0) - (a.resolution || 0));

			const organized: OrganizedVideo = {
				key: `${groupKey}-${mediaType}`,
				title: firstFormat.title || groupKey.split('/').pop() || 'Unknown',
				sourceUrl: firstFormat.originalUrl || firstFormat.downloadUrl || '',
				thumbnail: firstFormat.thumbnail || null,
				duration: firstFormat.duration || null,
				type: mediaType,
				qualities
			};

			result.push(organized);
		}
	}

	return result;
}

// ============================================================================
// CLEANUP
// ============================================================================

if (browser) {
	window.addEventListener('beforeunload', () => {
		apiCache.destroy();
	});
}
