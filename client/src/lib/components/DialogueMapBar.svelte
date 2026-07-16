<script lang="ts">
	/**
	 * Seekable dialogue-map (speech-energy peaks) over the video player.
	 * Peaks come from the transcription job; click seeks by x-position.
	 */
	import { i18n } from '$lib/i18n/index.svelte';

	const { t } = i18n;

	let {
		peaks,
		durationSeconds,
		currentTime = 0,
		visible = true,
		onSeek
	}: {
		peaks: number[];
		durationSeconds: number;
		currentTime?: number;
		visible?: boolean;
		onSeek: (seconds: number) => void;
	} = $props();

	let canvasEl: HTMLCanvasElement | null = $state(null);
	let trackEl: HTMLDivElement | null = $state(null);

	function draw() {
		const canvas = canvasEl;
		if (!canvas || !peaks.length) {
			return;
		}

		const dpr = typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1;
		const width = canvas.clientWidth || 300;
		const height = canvas.clientHeight || 72;
		canvas.width = Math.floor(width * dpr);
		canvas.height = Math.floor(height * dpr);

		const ctx = canvas.getContext('2d');
		if (!ctx) {
			return;
		}

		ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
		ctx.clearRect(0, 0, width, height);

		const n = peaks.length;
		const barW = Math.max(1, width / n);
		const progress =
			durationSeconds > 0 ? Math.min(1, Math.max(0, currentTime / durationSeconds)) : 0;

		for (let i = 0; i < n; i++) {
			const amp = Math.min(1, Math.max(0, peaks[i] ?? 0));
			const h = Math.max(1, amp * (height - 4));
			const x = (i / n) * width;
			const y = height - h;
			const played = i / n <= progress;
			ctx.fillStyle = played ? 'rgba(255,255,255,0.92)' : 'rgba(255,255,255,0.35)';
			ctx.fillRect(x, y, Math.max(1, barW - 0.5), h);
		}
	}

	$effect(() => {
		// Re-draw when peaks, time, or size-related state changes.
		void peaks;
		void currentTime;
		void durationSeconds;
		draw();
	});

	function seekFromEvent(e: MouseEvent | PointerEvent) {
		if (!trackEl || durationSeconds <= 0) {
			return;
		}
		const rect = trackEl.getBoundingClientRect();
		const ratio = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
		onSeek(ratio * durationSeconds);
	}
</script>

{#if peaks.length && durationSeconds > 0}
	<div class="ds-dialogue-map" data-visible={visible ? 'true' : 'false'}>
		<div
			bind:this={trackEl}
			class="ds-dialogue-map__track"
			role="slider"
			tabindex="0"
			aria-label={t('dialogueMap.aria')}
			aria-valuemin={0}
			aria-valuemax={Math.round(durationSeconds)}
			aria-valuenow={Math.round(currentTime)}
			onclick={seekFromEvent}
			onkeydown={(e) => {
				if (e.key === 'ArrowLeft') {
					onSeek(Math.max(0, currentTime - 5));
				} else if (e.key === 'ArrowRight') {
					onSeek(Math.min(durationSeconds, currentTime + 5));
				}
			}}
		>
			<canvas bind:this={canvasEl} class="ds-dialogue-map__canvas"></canvas>
		</div>
	</div>
{/if}
