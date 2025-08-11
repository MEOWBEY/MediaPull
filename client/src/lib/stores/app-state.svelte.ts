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

export interface ProcessedVideo extends VideoFormat {
	processingTime?: number;
	downloadUrl: string;
	id: string;
	processedAt: number;
	status: 'processing' | 'completed' | 'failed';
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
			type: 'video' | 'audio' | 'hls' | 'dash' | 'subtitle';
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
	processing = $state<boolean>(false);
	extracting = $state<boolean>(false);
	processingQueue = createReactiveSet<string>();

	// Data states
	processedVideos = $state<ProcessedVideo[]>([]);
	extractedData = $state<ExtractedVideoData | null>(null);

	// Error states
	processingError = $state<string | null>(null);
	extractionError = $state<string | null>(null);

	// UI preferences
	preferences = $state({
		theme: 'system' as 'light' | 'dark' | 'system',
		viewMode: 'list' as 'grid' | 'list',
		sortBy: 'date' as 'name' | 'date' | 'size' | 'quality',
		sortOrder: 'desc' as 'asc' | 'desc',
		showThumbnails: true,
		animationsEnabled: true,
		compactMode: false,
		muteByDefault: true,
		preloadMetadata: true,
		useProxy: true,
		showHlsDownloadButton: false,
		cacheEnabled: true,
		autoClearCache: false,
		highContrast: false,
		keyboardShortcuts: true
	});

	private readonly storageKeys = {
		processedVideos: 'directlinker_processed_videos_v2',
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
			const storedProcessed = localStorage.getItem(this.storageKeys.processedVideos);
			if (storedProcessed) {
				const parsed = JSON.parse(storedProcessed);
				const dayAgo = Date.now() - 24 * 60 * 60 * 1000;
				this.processedVideos = parsed.filter((v: ProcessedVideo) => v.processedAt > dayAgo);
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
		this.processedVideos.length = 0;
		this.extractedData = null;
		this.processingError = null;
		this.extractionError = null;
		this.processingQueue.clear();
		this.clearPersistedData();
	}

	clearErrors(): void {
		this.processingError = null;
		this.extractionError = null;
	}

	addProcessedVideo(video: ProcessedVideo): void {
		video.processedAt = Date.now();
		video.status = 'completed';

		const existingIndex = this.processedVideos.findIndex((v) => v.id === video.id);
		if (existingIndex !== -1) {
			this.processedVideos[existingIndex] = video;
		} else {
			this.processedVideos.unshift(video);
		}

		if (this.processedVideos.length > 50) {
			this.processedVideos = this.processedVideos.slice(0, 50);
		}

		this.saveProcessedVideos();
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

	clearProcessedVideos(): void {
		this.processedVideos.length = 0;
		if (browser) {
			localStorage.removeItem(this.storageKeys.processedVideos);
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

	getSortedProcessedVideos(): ProcessedVideo[] {
		const sorted = [...this.processedVideos];

		sorted.sort((a, b) => {
			let comparison = 0;

			switch (this.preferences.sortBy) {
				case 'name':
					comparison = (a.filename || '').localeCompare(b.filename || '');
					break;
				case 'date':
					comparison = (a.processedAt || 0) - (b.processedAt || 0);
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
	private saveProcessedVideos(): void {
		if (!browser) return;
		try {
			localStorage.setItem(this.storageKeys.processedVideos, JSON.stringify(this.processedVideos));
		} catch (error) {
			console.warn('Failed to save processed videos:', error);
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
// UTILITY FUNCTIONS
// ============================================================================

export function organizeVideosBySourceAndType(formats: VideoFormat[]): Record<string, VideoGroup> {
	if (!formats || formats.length === 0) return {};

	const sourceGroups: Record<string, VideoGroup> = {};

	for (const video of formats) {
		const groupKey = extractGroupKey(video);
		const videoType = getVideoType(video);
		const resolution = formatResolution(video);

		if (!sourceGroups[groupKey]) {
			sourceGroups[groupKey] = {
				groupKey,
				title: video.title || groupKey.split('/').pop() || 'Unknown Video',
				sourceUrl: video.originalUrl || '',
				types: {},
				thumbnail: video.thumbnail,
				duration: video.duration
			};
		}

		if (!sourceGroups[groupKey].types[videoType]) {
			sourceGroups[groupKey].types[videoType] = {
				type: videoType as unknown as 'video' | 'audio' | 'hls' | 'dash' | 'subtitle',
				formats: {},
				bestQuality: undefined
			};
		}

		sourceGroups[groupKey].types[videoType].formats[resolution] = video;

		const currentBest = sourceGroups[groupKey].types[videoType].bestQuality;
		if (!currentBest || compareQuality(video, currentBest) > 0) {
			sourceGroups[groupKey].types[videoType].bestQuality = video;
		}
	}

	return sourceGroups;
}

function extractGroupKey(video: VideoFormat): string {
	try {
		const url = new URL(video.originalUrl || '');
		const path = url.pathname.split('/');
		const filename = path[path.length - 1];
		const baseName = filename.split('-')[0];
		return `${url.hostname}/${baseName}`;
	} catch {
		return video.id;
	}
}

function getVideoType(video: VideoFormat): 'video' | 'audio' | 'hls' | 'dash' | 'subtitle' {
	if (video.isHLS || video.protocol === 'hls' || video.extension === 'm3u8') {
		return 'hls';
	}

	if (video.protocol === 'dash' || video.extension === 'mpd') {
		return 'dash';
	}

	const audioFormats = ['mp3', 'aac', 'ogg', 'wav', 'flac', 'm4a', 'opus'];
	if (audioFormats.includes(video.extension?.toLowerCase() || '')) {
		return 'audio';
	}

	const subtitleFormats = ['srt', 'vtt', 'ass', 'ssa'];
	if (subtitleFormats.includes(video.extension?.toLowerCase() || '')) {
		return 'subtitle';
	}

	return 'video';
}

function formatResolution(video: VideoFormat): string {
	if (video.height) {
		return `${video.height}p`;
	}
	if (video.resolution?.includes('x')) {
		const height = video.resolution.split('x')[1];
		return `${height}p`;
	}
	return video.resolution || video.quality || 'Unknown';
}

function compareQuality(a: VideoFormat, b: VideoFormat): number {
	const getQualityScore = (video: VideoFormat): number => {
		const height = video.height || parseInt(video.resolution?.split('x')[1] || '0') || 0;
		const bitrate = video.bitrate || 0;
		return height * 1000 + bitrate;
	};

	return getQualityScore(a) - getQualityScore(b);
}

// ============================================================================
// CLEANUP
// ============================================================================

if (browser) {
	window.addEventListener('beforeunload', () => {
		apiCache.destroy();
	});
}
