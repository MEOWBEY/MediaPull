import { writable } from 'svelte/store';

export interface ProcessingResult {
	success: boolean;
	filename?: string;
	size?: string;
	quality?: string;
	error?: string;
	downloadUrl?: string;
	videoSrc?: string;
}

export interface ProcessedVideo {
	id: string;
	originalUrl: string;
	filename: string;
	downloadUrl: string;
	videoSrc?: string;
	processedAt: string;
	quality: string;
	format: string;
	fileSize?: number;
	duration?: number;
	resolution?: string;
	fps?: number;
	bitrate?: number;
	videoCodec?: string;
	audioCodec?: string;
	thumbnail?: string;
	processingTime?: number;
	method?: string;
}

export interface ExtractedVideo {
	id: string;
	quality: string;
	resolution: string;
	width: number;
	height: number;
	fps?: number;
	fileSize?: number;
	extension: string;
	protocol: string;
	videoCodec?: string;
	audioCodec?: string;
	bitrate?: number;
	originalUrl: string;
	downloadUrl: string;
	isHLS: boolean;
	hasDRM: boolean;
}

export interface VideoData {
	duration: number;
	formats: ExtractedVideo[];
	totalFormats: number;
	extractedAt: string;
	sourceUrl: string;
}

export interface LogEntry {
	time: string;
	message: string;
	type: 'info' | 'success' | 'error' | 'warn' | 'debug';
	id: string;
}

export interface ProgressInfo {
	operation: string;
	percent: number;
	details: Record<string, any>;
	isActive: boolean;
}

// Core state
export const videoUrl = writable('');
export const processing = writable(false);
export const extracting = writable(false);

// Results and data
export const result = writable<ProcessingResult | null>(
	typeof localStorage !== 'undefined' && localStorage.getItem('dl-last-result')
		? JSON.parse(localStorage.getItem('dl-last-result')!)
		: null
);

// Processed videos with persistence
export const processedVideos = writable<ProcessedVideo[]>(
	typeof localStorage !== 'undefined' && localStorage.getItem('dl-processed-videos')
		? JSON.parse(localStorage.getItem('dl-processed-videos')!)
		: []
);

// Extracted video data with persistence
export const extractedVideoData = writable<VideoData | null>(
	typeof localStorage !== 'undefined' && localStorage.getItem('dl-extracted-video-data')
		? JSON.parse(localStorage.getItem('dl-extracted-video-data')!)
		: null
);

// UI state - these should not be persisted
export const copySuccess = writable('');
export const previewStates = writable(new Map<string, boolean>());
export const processingVideos = writable(new Set<string>());
export const extractionError = writable<string | null>(null);

// Auto-sync result to localStorage
result.subscribe(($res) => {
	if (typeof localStorage !== 'undefined') {
		if ($res) {
			localStorage.setItem('dl-last-result', JSON.stringify($res));
		} else {
			localStorage.removeItem('dl-last-result');
		}
	}
});

// Auto-sync processed videos to localStorage
processedVideos.subscribe(($videos) => {
	if (typeof localStorage !== 'undefined') {
		if ($videos.length > 0) {
			localStorage.setItem('dl-processed-videos', JSON.stringify($videos));
		} else {
			localStorage.removeItem('dl-processed-videos');
		}
	}
});

// Auto-sync extracted video data to localStorage
extractedVideoData.subscribe(($data) => {
	if (typeof localStorage !== 'undefined') {
		if ($data) {
			localStorage.setItem('dl-extracted-video-data', JSON.stringify($data));
		} else {
			localStorage.removeItem('dl-extracted-video-data');
		}
	}
});

// Logs with auto-cleanup
export const logs = writable<LogEntry[]>([]);
export const maxLogs = writable(100);

// Progress tracking
export const progress = writable<ProgressInfo>({
	operation: '',
	percent: 0,
	details: {},
	isActive: false
});

// Log management functions
export function addLog(message: string, type: LogEntry['type'] = 'info') {
	const newLog: LogEntry = {
		time: new Date().toLocaleTimeString(),
		message,
		type,
		id: Date.now().toString() + Math.random().toString(36).substr(2, 9)
	};

	logs.update((currentLogs) => {
		const updatedLogs = [...currentLogs, newLog];
		return updatedLogs.slice(-100);
	});
}

// Processed videos management
export function addProcessedVideo(video: ProcessedVideo) {
	processedVideos.update((videos) => {
		// Check if video already exists (by originalUrl and quality)
		const existingIndex = videos.findIndex((v) => 
			v.originalUrl === video.originalUrl && v.quality === video.quality
		);
		
		if (existingIndex >= 0) {
			// Update existing video
			videos[existingIndex] = { ...videos[existingIndex], ...video };
			return [...videos];
		} else {
			// Add new video to the beginning of the list
			return [video, ...videos];
		}
	});
}

export function removeProcessedVideo(id: string) {
	processedVideos.update((videos) => videos.filter((v) => v.id !== id));
}

export function clearProcessedVideos() {
	processedVideos.set([]);
}

// Extracted video data management
export function setExtractedVideoData(data: VideoData) {
	extractedVideoData.set({
		...data,
		extractedAt: new Date().toISOString()
	});
	
	// Initialize preview states for all formats - DEFAULT TRUE for extracted videos
	previewStates.set(new Map(data.formats.map((format) => [format.id, true])));
}

export function clearExtractedVideoData() {
	extractedVideoData.set(null);
	previewStates.set(new Map());
}

// Preview state management - Fixed toggle functionality
export function togglePreview(videoId: string) {
	previewStates.update((states) => {
		const newStates = new Map(states);
		const currentState = newStates.get(videoId) ?? true; // Default to true for extracted videos
		newStates.set(videoId, !currentState);
		return newStates;
	});
}

export function setPreviewState(videoId: string, state: boolean) {
	previewStates.update((states) => {
		const newStates = new Map(states);
		newStates.set(videoId, state);
		return newStates;
	});
}

// Processing state management
export function addProcessingVideo(url: string) {
	processingVideos.update((videos) => {
		const newSet = new Set(videos);
		newSet.add(url);
		return newSet;
	});
}

export function removeProcessingVideo(url: string) {
	processingVideos.update((videos) => {
		const newSet = new Set(videos);
		newSet.delete(url);
		return newSet;
	});
}

// Copy success management
export function setCopySuccess(id: string, duration = 2000) {
	copySuccess.set(id);
	setTimeout(() => {
		copySuccess.update((current) => current === id ? '' : current);
	}, duration);
}

// Progress management
export function setProgress(operation: string, percent: number, details: Record<string, any> = {}) {
	progress.set({
		operation,
		percent,
		details,
		isActive: percent < 100
	});
}

export function resetProgress() {
	progress.set({
		operation: '',
		percent: 0,
		details: {},
		isActive: false
	});
}

// Reset all state
export function resetAllState() {
	result.set(null);
	extractionError.set(null);
	clearExtractedVideoData();
	resetProgress();
	copySuccess.set('');
}