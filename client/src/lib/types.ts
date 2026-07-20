/** Shared domain types for the MediaPull client. */

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

/** An existing caption track the source already provides (yt-dlp's own
 *  subtitles/automatic_captions metadata) — free to use, no transcription
 *  pipeline needed when one of these already matches. */
export interface SubtitleTrack {
	lang: string;
	label: string;
	url: string;
	ext: string;
	isAuto: boolean;
}

/** One format "kind" of a video (progressive MP4, HLS, a separate audio-only
 *  stream, ...) -- a `GroupedVideo` can have several, rendered as tabs since
 *  they're all the same underlying source. */
export interface FormatGroup {
	type: MediaType;
	qualities: VideoFormat[];
}

export interface GroupedVideo {
	id?: string;
	title?: string;
	thumbnail?: string;
	duration?: number;
	formatGroups: FormatGroup[];
	height?: number;
	width?: number;
	upload_date?: string;
	aspect_ratio?: number;
	webpage_url?: string;
	subtitleTracks?: SubtitleTrack[];
	/** Generated/reused subtitle track, persisted so a refresh doesn't lose it. */
	subtitleTrack?: SubtitleTrackResult;
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
	/** Opaque token standing in for this format's auth cookies, minted by
	 *  `resolveVideoCookieTokens` so cookies never enter the (shareable) proxy
	 *  URL. Attached client-side after extraction; absent when no cookies apply. */
	cookieToken?: string;
}

export interface IncomingVideo {
	formats?: IncomingFormat[];
	metadata?: Partial<VideoMetadata>;
	subtitleTracks?: SubtitleTrack[];
}

export interface Preferences {
	theme: 'light' | 'dark' | 'system';
	/** Result-card layout: `'grid'` = 1 col on mobile / 2 cols on desktop;
	 *  `'row'` = one full-width horizontal card per row (player start-side,
	 *  details end-side) on desktop, stacked on mobile. */
	layoutList: 'grid' | 'row';
	/** Route media through `/proxy-video` (Referer/Cookie/UA the player can't set).
	 *  Off = direct CDN URLs — faster, but breaks many gated sources. */
	enableProxyForVideoExtract: boolean;
	enableVideoMute: boolean;
	/** Ask the player to preload metadata only (not the full stream) — saves data. */
	enableVideoPreloadMetadata: boolean;
	showVideoThumbnail: boolean;
	/** Show a download action on HLS tabs (playlist only, not a single file). */
	showHlsTypeDownloadButton: boolean;
	/** Show the per-group export buttons (Links .txt / Playlist .m3u) in the
	 *  source-group header. Off by default -- most users just want the source
	 *  URL + refresh/remove; power users can turn the exports back on. */
	showExportButtons: boolean;
	/** Show adaptive video-only (no-audio) qualities, e.g. YouTube >720p. Off by default. */
	showVideoOnlyFormats: boolean;
	/** Hide caption lines shorter than this many words from the subtitle
	 *  panel only (the video track still shows every line). 0 = show all. */
	subtitlePanelMinWords: number;
	/** Which extraction endpoint the URL input routes to. `'auto'` (the
	 *  default) tries video first and silently falls back to gallery if
	 *  nothing comes back -- see `ExtractionController.extractLinks`. Force
	 *  `'video'`/`'gallery'` from Preferences to always use one endpoint. */
	contentTypeMode: 'auto' | 'video' | 'gallery';
}

// ----- Image galleries (gallery-dl) --------------------------------------

/** One image as it arrives from the backend (pre-normalization). */
export interface IncomingGalleryImage {
	url?: string;
	width?: number;
	height?: number;
	filesize?: number;
	ext?: string;
	httpHeaders?: Record<string, string> | null;
	/** Opaque cookie token (see `IncomingFormat.cookieToken`). */
	cookieToken?: string;
}

export interface IncomingGallery {
	title?: string;
	webpageUrl?: string;
	images?: IncomingGalleryImage[];
	/** Entries gallery-dl reported as errors or in an unrecognized shape --
	 *  a partially-failed gallery (common on Instagram/X without cookies)
	 *  looks different from a fully successful one. */
	skippedCount?: number;
	/** Soft notices (login needed, degraded quality, truncated, …). */
	warnings?: GalleryWarning[];
}

/** A normalized image ready for rendering/download. The client builds `url`
 *  (the proxied link, used for display/download/copy) from `sourceUrl` +
 *  `httpHeaders` the same way video formats build `proxiedVideoUrl`. */
export interface ImageAsset {
	url: string;
	sourceUrl: string;
	width: number;
	height: number;
	filesize: number;
	ext: string;
}

export interface GroupedGallery {
	id?: string;
	title?: string;
	webpage_url?: string;
	images: ImageAsset[];
	/** Entries gallery-dl couldn't extract for this source (see
	 *  `IncomingGallery.skippedCount`). */
	skippedCount?: number;
	warnings?: GalleryWarning[];
}

/** One subtitle line with its timing. */
export interface SubtitleSegment {
	start: number;
	end: number;
	text: string;
}

/** A resolved subtitle track for a video -- either transcribed via Groq or
 *  reused from the source's own captions. Persisted on the `GroupedVideo`
 *  itself (see `GroupedVideo.subtitleTrack`) so it survives a page refresh
 *  instead of re-fetching/re-transcribing, and disappears automatically
 *  when the video is removed (same lifecycle, same object). */
export interface SubtitleTrackResult {
	language: string;
	segments: SubtitleSegment[];
	vttUrl?: string;
	srtUrl?: string;
	/** Normalized 0..1 peaks (~1 per 100ms) for the dialogue-map seek bar. */
	dialogueMap?: number[] | null;
}

/** One non-fatal gallery extract notice (quality, login, rate-limit, …). */
export interface GalleryWarning {
	code: string;
	message: string;
}

/** Wire shape of `GET /transcribe/{jobId}` (NOT wrapped in `ApiEnvelope` —
 *  see `postJson`/`getJson` in `api/client.ts`). */
export interface TranscribeStatus {
	jobId: string;
	status: 'queued' | 'downloading' | 'chunking' | 'transcribing' | 'finalizing' | 'done' | 'error' | 'cancelled';
	progress: number;
	stepLabel: string;
	/** Fine-grained sub-stage code, more specific than `status` — the client
	 *  maps it to its own localized text. Absent on older servers. */
	detail?:
		| 'planning'
		| 'downloading_source'
		| 'extracting'
		| 'compressing'
		| 'transcribing'
		| 'building_subtitles'
		| 'dialogue_map'
		| 'waveform' // legacy server detail
		| null;
	/** Transcription chunk counters (0 until that stage) — the client builds
	 *  its own localized "x of y" stage text from these. */
	chunksDone?: number;
	chunksTotal?: number;
	error?: string | null;
	result?: {
		language: string;
		vttUrl: string;
		srtUrl: string;
		dialogueMap?: number[] | null;
		/** @deprecated server used to send this name */
		waveform?: number[] | null;
	} | null;
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

/** Same envelope shape as `ApiEnvelope`, but `/extract-gallery` wraps its
 *  payload under `gallery` instead of `video`. */
export interface GalleryApiEnvelope<T> {
	success: boolean;
	error?: string;
	details?: string;
	detail?: string | Array<{ msg?: string }>;
	gallery: T;
}
