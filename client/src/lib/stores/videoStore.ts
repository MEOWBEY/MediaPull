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
	filesize: string;
}

export interface LogEntry {
	time: string;
	message: string;
	type: 'info' | 'success' | 'error' | 'warn' | 'debug';
	id: string;
}

export interface ExtractedLink {
	format: string;
	quality: string;
	size: string;
	url: string;
	type: 'extract' | 'direct';
	buttonText: string;
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
		// Check if video already exists (by originalUrl)
		const existingIndex = videos.findIndex((v) => v.originalUrl === video.originalUrl);
		if (existingIndex >= 0) {
			// Update existing video
			videos[existingIndex] = video;
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

export function resetProgress() {
	progress.set({
		operation: '',
		percent: 0,
		details: {},
		isActive: false
	});
}
