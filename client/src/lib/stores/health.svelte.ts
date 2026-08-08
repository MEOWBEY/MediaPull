/**
 * Fetches /health once on app boot and exposes server capability flags.
 * Components read these to show/hide features without separate API calls.
 */

import { getJson } from '$lib/api/client';

interface HealthData {
	transcribeEnabled: boolean;
	mediaMaxBytes: number;
	localFilesEnabled: boolean;
	splitAudioEnabled: boolean;
	ffmpegAvailable: boolean;
}

const DEFAULTS: HealthData = {
	transcribeEnabled: false,
	mediaMaxBytes: 300_000_000,
	localFilesEnabled: true,
	splitAudioEnabled: false,
	ffmpegAvailable: false,
};

class HealthStore {
	transcribeEnabled = $state(DEFAULTS.transcribeEnabled);
	mediaMaxBytes = $state(DEFAULTS.mediaMaxBytes);
	localFilesEnabled = $state(DEFAULTS.localFilesEnabled);
	splitAudioEnabled = $state(DEFAULTS.splitAudioEnabled);
	ffmpegAvailable = $state(DEFAULTS.ffmpegAvailable);
	loaded = $state(false);

	async load(): Promise<void> {
		try {
			const data = await getJson<HealthData>('/health');

			this.transcribeEnabled = data.transcribeEnabled ?? DEFAULTS.transcribeEnabled;
			this.mediaMaxBytes = data.mediaMaxBytes ?? DEFAULTS.mediaMaxBytes;
			this.localFilesEnabled = data.localFilesEnabled ?? DEFAULTS.localFilesEnabled;
			this.splitAudioEnabled = data.splitAudioEnabled ?? DEFAULTS.splitAudioEnabled;
			this.ffmpegAvailable = data.ffmpegAvailable ?? DEFAULTS.ffmpegAvailable;
		} catch {
			// Health probe failure is non-fatal — fall back to safe defaults
			// (features appear disabled; the user can still extract URLs).
		} finally {
			this.loaded = true;
		}
	}
}

export const health = new HealthStore();
