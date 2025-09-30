<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import Plyr from 'plyr';
	import Hls from 'hls.js';
	import 'plyr/dist/plyr.css';

	import { appStore } from '$lib/stores/app-state.svelte';

	let { poster = '', qualities = [] } = $props();

	let preferences = $derived(appStore.preferences);

	let videoElement: HTMLVideoElement;
	let player: Plyr | null = null;
	let hls: Hls | null = null;

	onMount(() => {
		if (!qualities.length) return;

		initializePlayer();
		loadVideo();

		return cleanup;
	});

	function initializePlayer() {
		player = new Plyr(videoElement, {
			controls: [
				'play-large',
				'play',
				'progress',
				'current-time',
				'duration',
				'mute',
				'volume',
				'settings',
				'fullscreen'
			],
			settings: ['quality', 'speed'],
			quality: {
				default: qualities[0].resolution,
				options: qualities.map((q) => q.resolution),
				forced: true,
				onChange: handleQualityChange
			},
			muted: preferences.enableVideoMute,
			ratio: '16:9',
			autopause: false,
			resetOnEnd: false
		});
		if (preferences.showVideoThumbnail && poster) {
			player.poster = poster;
		}
	}

	function loadVideo() {
		const src = getSourceUrl(qualities[0]);

		if (src.includes('.m3u8')) {
			if (Hls.isSupported()) {
				loadHLS(src);
			} else if (videoElement.canPlayType('application/vnd.apple.mpegurl')) {
				videoElement.src = src;
			}
		} else {
			videoElement.src = src;
		}
	}

	function loadHLS(src: string) {
		if (hls) hls.destroy();

		hls = new Hls({
			enableWorker: true,
			lowLatencyMode: false
		});

		hls.loadSource(src);
		hls.attachMedia(videoElement);

		hls.on(Hls.Events.ERROR, (event, data) => {
			if (!data.fatal) return;

			if (data.type === Hls.ErrorTypes.NETWORK_ERROR) {
				hls?.startLoad();
			} else if (data.type === Hls.ErrorTypes.MEDIA_ERROR) {
				hls?.recoverMediaError();
			}
		});
	}

	function handleQualityChange(newQuality: number) {
		const quality = qualities.find((q) => q.resolution === newQuality);
		if (!quality || !player) return;

		const currentTime = player.currentTime;
		const wasPlaying = !player.paused;
		const src = getSourceUrl(quality);

		if (src.includes('.m3u8') && Hls.isSupported()) {
			loadHLS(src);
		} else {
			videoElement.src = src;
		}

		videoElement.addEventListener(
			'loadedmetadata',
			() => {
				if (!player) return;
				player.currentTime = currentTime;
				if (wasPlaying) player.play();
			},
			{ once: true }
		);
	}

	function getSourceUrl(quality: any): string {
		return preferences.enableProxyForVideoExtract
			? quality.proxiedVideoUrl
			: quality.sourceVideoUrl;
	}

	function cleanup() {
		hls?.destroy();
		player?.destroy();
		hls = null;
		player = null;
	}

	onDestroy(cleanup);
</script>

<div class="relative aspect-video w-full rounded-t-lg bg-black">
	<video
		bind:this={videoElement}
		preload={preferences.enableVideoPreloadMetadata ? 'metadata' : 'none'}
		playsinline
		crossorigin="anonymous"
	>
		<track kind="captions" />
	</video>
</div>

<style>
	:global(.plyr) {
		position: relative;
		max-width: 800px;
		margin: 0 auto;
		border-radius: 10px;
		overflow: hidden;
	}

	:global(.plyr__progress__container) {
		position: absolute;
		top: 10px;
		left: 12px;
		right: 12px;
		width: auto;
	}

	:global(.plyr__controls) {
		position: absolute;
		bottom: 0;
		width: 100%;
		background: rgba(0, 0, 0, 0.6);
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 8px 12px;
	}
	:global(.plyr__volume input[type='range']) {
		display: none;
	}
	/* Time adjustments for small screens */
	@media (max-width: 480px) {
		:global(.plyr__progress__container) {
			top: 0px;
			left: 8px;
			right: 8px;
		}

		:global(.plyr__time) {
			position: absolute;
			left: 87px !important;
		}

		:global(.plyr__time--current) {
			position: absolute;
			left: 41px !important;
		}
	}

	@media (max-width: 767px) {
		:global(.plyr__time) {
			display: inline-block !important;
		}
	}

	:global(.plyr__time) {
		position: absolute;
		left: 95px;
	}

	:global(.plyr__time--current) {
		position: absolute;
		left: 50px;
	}
</style>
