/** Shared domain types for the DirectStream client. Single source of truth. */

export type MediaType =
	| 'video/mp4'
	| 'video/webm'
	| 'video/x-matroska'
	| 'video/quicktime'
	| 'video/x-msvideo'
	| 'application/x-mpegURL'
	| 'application/dash+xml'
	| 'audio/mpeg'
	| 'audio/aac'
	| 'audio/ogg'
	| 'audio/wav'
	| 'audio/flac'
	| 'audio/mp4'
	| 'audio/opus'
	| (string & {});

export interface VideoFormat {
	proxiedVideoUrl: string;
	sourceVideoUrl: string;
	ext: string;
	format_id: string;
	protocol: string;
	resolution: number;
	tbr: number;
	filesize: number;
	/** Adaptive stream with video but no audio (e.g. YouTube >720p). */
	videoOnly: boolean;
}

export interface VideoMetadata {
	id: string;
	title: string;
	thumbnail: string;
	duration: number;
	width: number;
	height: number;
	aspect_ratio: number;
	upload_date: string;
	webpage_url: string;
}

export interface GroupedVideo {
	id?: string;
	title?: string;
	thumbnail?: string;
	duration?: number;
	type: MediaType;
	qualities: VideoFormat[];
	height?: number;
	width?: number;
	upload_date?: string;
	aspect_ratio?: number;
	webpage_url?: string;
}

/** Raw shapes as they arrive from the backend (pre-grouping). The client builds
 *  `proxiedVideoUrl` from `sourceVideoUrl` + `httpHeaders`. */
export interface IncomingFormat {
	sourceVideoUrl?: string;
	httpHeaders?: Record<string, string> | null;
	ext?: string;
	tbr?: number | string;
	filesize?: number;
	protocol?: string;
	format_id?: string;
	resolution?: number | string;
	videoOnly?: boolean;
}

export interface IncomingVideo {
	formats?: IncomingFormat[];
	metadata?: Partial<VideoMetadata>;
}

export interface Preferences {
	theme: 'light' | 'dark' | 'system';
	layoutList: 'grid' | 'list';
	videoSortField: 'name' | 'size' | 'quality';
	videoSortOrder: 'asc' | 'desc';
	enableAnimations: boolean;
	enableCompact: boolean;
	enableProxyForVideoExtract: boolean;
	enableVideoMute: boolean;
	enableVideoPreloadMetadata: boolean;
	showVideoThumbnail: boolean;
	showHlsTypeDownloadButton: boolean;
	/** Show adaptive video-only (no-audio) qualities, e.g. YouTube >720p. Off by default. */
	showVideoOnlyFormats: boolean;
}

/** Envelope returned by the backend. `error`/`details` are our own fields; FastAPI
 *  raises (`HTTPException`, validation) surface as `detail` (string or an array of
 *  `{msg}` for 422), so the client reads all of them to show a real message. */
export interface ApiEnvelope<T> {
	success: boolean;
	error?: string;
	details?: string;
	detail?: string | Array<{ msg?: string }>;
	video: T;
}
