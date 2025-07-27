<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import videojs from 'video.js';
	import 'video.js/dist/video-js.css';

	let {
		src,
		controls = true,
		autoplay = false,
		poster = '',
		preload = 'metadata',
		aspectRatio = '16:9',
		maxWidth = '100%',
		maxHeight = '70vh',
		fluid = true,
		responsive = true
	} = $props();

	let player: videojs.Player;
	let videoElement: HTMLVideoElement;
	let containerElement: HTMLDivElement;
	let isFullscreen = $state(false);

	function findType(url: string): string {
		const lowerUrl = url.toLowerCase();
		if (lowerUrl.includes('.m3u8')) return 'application/x-mpegURL';
		if (lowerUrl.includes('.mp4')) return 'video/mp4';
		if (lowerUrl.includes('.webm')) return 'video/webm';
		if (lowerUrl.includes('.ogv') || lowerUrl.includes('.ogg')) return 'video/ogg';
		if (lowerUrl.includes('.mov')) return 'video/quicktime';
		if (lowerUrl.includes('.ts')) return 'video/mp2t';
		if (lowerUrl.includes('.avi')) return 'video/x-msvideo';
		return 'video/mp4';
	}

	function calculateAspectRatio(ratio: string): number {
		const [width, height] = ratio.split(':').map(Number);
		return (height / width) * 100;
	}

	function handleResize() {
		if (player && responsive) {
			player.responsive(true);
		}
	}

	onMount(() => {
		const type = findType(src);

		// Initialize Video.js player
		player = videojs(videoElement, {
			controls,
			autoplay,
			preload,
			poster,
			fluid,
			responsive,
			aspectRatio,
			sources: [{ src, type }],
			playbackRates: [0.5, 1, 1.25, 1.5, 2],
			plugins: {
				// Add quality selector if needed
			}
		});

		// Handle fullscreen changes
		player.on('fullscreenchange', () => {
			isFullscreen = player.isFullscreen();
		});

		// Handle player ready
		player.ready(() => {
			console.log('Player is ready with type:', type);

			// Set initial sizing
			if (responsive) {
				player.responsive(true);
			}
		});

		// Add resize listener
		window.addEventListener('resize', handleResize);

		return () => {
			window.removeEventListener('resize', handleResize);
		};
	});

	onDestroy(() => {
		if (player) {
			player.dispose();
		}
	});

	// Reactive statement to update player when src changes
	$effect(() => {
		if (player && src) {
			const type = findType(src);
			player.src({ src, type });
		}
	});
</script>

<div
	bind:this={containerElement}
	class="video-player-container"
	class:fullscreen={isFullscreen}
	style="
		max-width: {maxWidth};
		max-height: {maxHeight};
		--aspect-ratio: {calculateAspectRatio(aspectRatio)}%;
	"
>
	<div class="video-wrapper">
		<video bind:this={videoElement} id="video-player" class="video-js vjs-default-skin" playsinline>
		</video>
	</div>
</div>

<style>
	.video-player-container {
		position: relative;
		width: 100%;
		margin: 0 auto;
		background: #000;
		border-radius: 8px;
		overflow: hidden;
		box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
	}

	.video-wrapper {
		position: relative;
		width: 100%;
		height: 0;
		padding-bottom: var(--aspect-ratio);
		background: #000;
	}

	.video-wrapper :global(.video-js) {
		position: absolute;
		top: 0;
		left: 0;
		width: 100% !important;
		height: 100% !important;
		border-radius: inherit;
	}

	/* Fullscreen styles */
	.fullscreen {
		position: fixed !important;
		top: 0 !important;
		left: 0 !important;
		width: 100vw !important;
		height: 100vh !important;
		max-width: none !important;
		max-height: none !important;
		z-index: 9999 !important;
		border-radius: 0 !important;
	}

	.fullscreen .video-wrapper {
		padding-bottom: 0;
		height: 100%;
	}

	/* Responsive breakpoints */
	@media (max-width: 768px) {
		.video-player-container {
			border-radius: 0;
			box-shadow: none;
		}
	}

	@media (max-width: 480px) {
		.video-player-container {
			--aspect-ratio: 56.25%; /* Force 16:9 on mobile */
		}
	}
</style>
