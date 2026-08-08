<script lang="ts">
	import Download from '@lucide/svelte/icons/download';
	import Loader2 from '@lucide/svelte/icons/loader-2';
	import Music from '@lucide/svelte/icons/music';
	import X from '@lucide/svelte/icons/x';
	import { onMount } from 'svelte';
	import { toast } from 'svelte-sonner';

	import { cancelSplitAudio, pollSplitAudio, splitAudioDownloadUrl } from '$lib/api/split-audio';
	import { resolveApiUrl } from '$lib/config';
	import { i18n } from '$lib/i18n/index.svelte';
	import type { AudioSplitDone } from '$lib/stores/local-library.svelte';

	const { t } = i18n;

	let {
		run,
		filenameHint,
		persisted = null,
		onDone
	}: {
		/** Kicks off the split (local upload or server-side URL fetch); must
		 *  resolve with the server's exportId. */
		run: (signal: AbortSignal) => Promise<{ exportId: string }>;
		/** Fallback download name — the server's real filename wins when it
		 *  sends one. */
		filenameHint: string;
		/** A finished split restored from IndexedDB (re-verified on mount;
		 *  the server's mp3 only lives for SPLIT_AUDIO_TTL). */
		persisted?: AudioSplitDone | null;
		/** Reports done/cleared so the owner can persist the state. */
		onDone?: (state: AudioSplitDone | null) => void;
	} = $props();

	type SplitPhase = 'idle' | 'splitting' | 'done' | 'error';
	// The restored split is a one-shot seed (same closure trick as the cards'
	// `initial*` props) — re-verified against the server on mount below.
	const seedPersisted = () => persisted ?? null;
	let phase = $state<SplitPhase>(seedPersisted() ? 'done' : 'idle');
	let exportId = $state<string | null>(seedPersisted()?.exportId ?? null);
	let filename = $state<string | null>(seedPersisted()?.filename ?? null);
	let progress = $state(0);
	let stepLabel = $state('');
	let uploadingFile = $state(false);
	let controller: AbortController | null = null;
	let stopped = false;

	// Re-verify a restored split against the server: by the time the user
	// reopens (or even within the same session after a refresh) the TTL may
	// have expired — then the download button is meaningless.
	onMount(() => {
		if (!persisted || !exportId) {
			return;
		}
		void pollSplitAudio(exportId)
			.then((status) => {
				if (status.status === 'done') {
					phase = 'done';
					filename = status.filename ?? persisted?.filename ?? null;

					return;
				}
				phase = 'idle';
				exportId = null;
				onDone?.(null);
			})
			.catch(() => {
				phase = 'idle';
				exportId = null;
				onDone?.(null);
			});
	});

	async function split() {
		if (phase === 'splitting') {
			return;
		}

		controller?.abort();
		controller = new AbortController();
		stopped = false;
		phase = 'splitting';
		progress = 0;
		uploadingFile = true;
		toast.info(t('toast.audioSplitting'));

		try {
			const { exportId: id } = await run(controller.signal);

			uploadingFile = false;

			exportId = id;

			// Poll once immediately — short jobs finish before the first 1.2s sleep
			// so without this the progress jumps from 5% to done with no intermediate updates.
			{
				const first = await pollSplitAudio(id, { signal: controller.signal });

				progress = first.progress ?? 0;
				stepLabel = first.stepLabel || '';
				if (first.status === 'done') {
					phase = 'done';
					filename = first.filename ?? `${filenameHint}.mp3`;
					stopped = false;
					onDone?.({ state: 'done', exportId: id, filename });
					toast.success(t('toast.audioReady'));

					return;
				}
				if (first.status === 'error') {
					throw new Error(first.error ?? 'Audio split failed');
				}
			}

			// Poll until done (or the user cancels).
			while (!stopped) {
				await new Promise((r) => setTimeout(r, 1200));
				const status = await pollSplitAudio(id, { signal: controller.signal });

				progress = status.progress ?? 0;
				stepLabel = status.stepLabel || '';

				if (status.status === 'done') {
					phase = 'done';
					filename = status.filename ?? `${filenameHint}.mp3`;
					stopped = false;
					onDone?.({ state: 'done', exportId: id, filename });
					toast.success(t('toast.audioReady'));

					return;
				}
				if (status.status === 'error') {
					throw new Error(status.error ?? 'Audio split failed');
				}
			}
			phase = 'idle';
		} catch (err) {
			if ((err as Error)?.name === 'AbortError' || stopped) {
				phase = 'idle';
				uploadingFile = false;

				return;
			}
			phase = 'error';
			uploadingFile = false;
			const msg = (err as Error)?.message ?? '';

			// Surface the server's own error text (it carries the real ffmpeg
			// failure) instead of a generic toast, except the "no audio stream"
			// sentinel which maps to its own friendlier message.
			if (msg === 'no_audio_stream') {
				toast.error(t('toast.audioNoStream'));
			} else if (msg && msg !== 'Audio split failed') {
				toast.error(msg);
			} else {
				toast.error(t('toast.audioFailed'));
			}
		}
	}

	async function cancel() {
		if (phase !== 'splitting') {
			return;
		}
		stopped = true;
		uploadingFile = false;
		controller?.abort();
		controller = null;
		if (exportId) {
			// Best-effort: the server's ffmpeg may have already finished.
			void cancelSplitAudio(exportId).catch(() => {});
		}
		phase = 'idle';
		progress = 0;
	}

	function download() {
		if (!exportId) {
			return;
		}
		const url = resolveApiUrl(splitAudioDownloadUrl(exportId));

		const a = document.createElement('a');

		a.href = url;
		a.download = filename ?? 'audio.mp3';
		a.click();
	}

	// A split's mp3 only lives SPLIT_AUDIO_TTL on the server: by the time the
	// user gets back to the tab (or leaves it open past expiry), the "done"
	// button can point at a job the server already swept. Re-verify on click
	// and revert to the split button (so it can start again) when it's gone.
	async function downloadVerified() {
		if (!exportId) {
			return;
		}
		try {
			const status = await pollSplitAudio(exportId);

			if (status.status === 'done') {
				filename = status.filename ?? filename;
				download();

				return;
			}
		} catch {
			// The job is gone (404) — fall through to the reset below.
		}

		phase = 'idle';
		exportId = null;
		onDone?.(null);
		toast.info(t('toast.audioExpired'));
	}
</script>

<div class="flex w-full min-w-0 items-center gap-1.5 sm:w-auto sm:shrink">
	{#if phase === 'done'}
		<button
			type="button"
			onclick={downloadVerified}
			title={t('localFile.downloadAudio')}
			class="border-signal/40 bg-signal/15 text-signal animate-in fade-in flex w-full min-w-0 items-center justify-center gap-1.5 rounded-md border px-2.5 py-2 font-mono text-sm font-semibold transition-colors hover:bg-signal/25 sm:w-auto sm:justify-start sm:py-1.5"
		>
			<Download class="h-3.5 w-3.5 shrink-0" />
			<span class="truncate">{t('localFile.downloadAudio')}</span>
		</button>
	{:else if phase === 'splitting'}
		<div
			class="border-border/70 flex w-full min-w-0 items-center overflow-hidden rounded-md border sm:w-auto"
		>
			<span
				class="text-muted-foreground inline-flex min-w-0 flex-1 items-center gap-1 px-2 py-1.5 font-mono text-xs sm:flex-none"
				title={uploadingFile ? t('localFile.uploading') : (stepLabel || t('localFile.splittingAudio'))}
				role="status"
			>
				<Loader2 class="h-3 w-3 shrink-0 animate-spin" />
				<span class="inline min-w-0 max-w-48 truncate text-xs">{uploadingFile ? t('localFile.uploading') : (stepLabel || t('localFile.splittingAudio'))}</span
				>
				<span class="ms-auto tabular-nums sm:ms-0">{uploadingFile ? '' : `${Math.round(progress * 100)}%`}</span>
			</span>
			<button
				type="button"
				onclick={cancel}
				title={t('subtitles.cancel')}
				aria-label={t('subtitles.cancel')}
				class="border-border/70 text-muted-foreground hover:bg-muted hover:text-destructive flex shrink-0 items-center gap-1 border-s px-2 py-2 font-mono text-xs transition-colors sm:py-1.5"
			>
				<X class="h-3 w-3" />
				<span class="hidden sm:inline">{t('subtitles.cancel')}</span>
			</button>
		</div>
	{:else}
		<button
			type="button"
			onclick={split}
			title={t('localFile.splitAudioHint')}
			class="border-border/70 text-muted-foreground hover:bg-muted hover:text-foreground animate-in fade-in flex w-full min-w-0 items-center justify-center gap-1.5 rounded-md border px-2.5 py-2 font-mono text-sm transition-colors sm:w-auto sm:justify-start sm:py-1.5"
		>
			<Music class="h-3.5 w-3.5 shrink-0" />
			<span class="truncate">{t('localFile.splitAudio')}</span>
		</button>
	{/if}
</div>
