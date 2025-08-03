<script lang="ts">
	import 'vidstack/player/styles/default/theme.css';
	import 'vidstack/player/styles/default/layouts/video.css';

	import 'vidstack/player';
	import 'vidstack/player/layouts/default';
	import 'vidstack/player/ui';

	import Check from 'lucide-svelte/icons/check';
	import ChevronDown from 'lucide-svelte/icons/chevron-down';
	import Monitor from 'lucide-svelte/icons/monitor';
	import PictureInPicture2 from 'lucide-svelte/icons/picture-in-picture-2';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu/index.js';
	import { Button } from '$lib/components/ui/button/index.js';

	let {
		src,
		poster = '',
		autoplay = false,
		muted = false,
		preload = 'metadata',
		load = 'visible',
		showControls = true,
		volume = 0.8,
		playbackRate = 1.0,
		loopVideo = false,
		enablePiP = true,
		qualities = []
	} = $props();

	let player: any = $state();
	let currentSrc = $state(src);
	let selectedQuality = $state('');
	let isExternalQualityMenuOpen = $state(false);
	let currentVolume = $state(volume);
	let currentPlaybackRate = $state(playbackRate);

	function switchQuality(qualityOption: any) {
		if (!player || !qualityOption) return;

		currentSrc = qualityOption.src;
		selectedQuality = qualityOption.label;
	}

	function togglePictureInPicture() {
		if (!player || !enablePiP) return;

		try {
			if (document.pictureInPictureElement) {
				document.exitPictureInPicture();
			} else {
				player.requestPictureInPicture();
			}
		} catch (error) {
			console.warn('Picture-in-Picture not supported:', error);
		}
	}

	// Initialize with first available quality
	$effect(() => {
		if (qualities.length > 1) {
			const firstQuality = qualities[0];
			currentSrc = firstQuality.src;
			selectedQuality = firstQuality.label;
		}
	});

	// Update player properties when props change
	$effect(() => {
		if (player) {
			player.volume = currentVolume;
			player.playbackRate = currentPlaybackRate;
			player.loop = loopVideo;
		}
	});

	// Sync volume changes
	$effect(() => {
		currentVolume = volume;
	});

	// Sync playback rate changes
	$effect(() => {
		currentPlaybackRate = playbackRate;
	});
</script>

<div class="bg-background flex w-full flex-col gap-3">
	<!-- Video Player with Custom Controls -->
	<div class="video-container relative w-full">
		<media-player
			bind:this={player}
			keep-alive
			playsInline
			class="player"
			src={currentSrc}
			{preload}
			{load}
			viewType="video"
			{autoplay}
			{muted}
			loop={loopVideo}
			volume={currentVolume}
			playbackRate={currentPlaybackRate}
			crossorigin="anonymous"
		>
			<media-provider>
				<media-poster src={poster}></media-poster>
			</media-provider>
			{#if showControls}
				<media-video-layout></media-video-layout>
			{:else}
				<media-video-layout hideControls></media-video-layout>
			{/if}
		</media-player>
	</div>

	<!-- External Controls -->
	<div class="external-controls flex items-center justify-between gap-2">
		<!-- Quality Selector -->
		{#if qualities.length > 1}
			<DropdownMenu.Root bind:open={isExternalQualityMenuOpen}>
				<DropdownMenu.Trigger>
					<Button
						variant="outline"
						size="sm"
						class="min-w-28 justify-between gap-2"
						aria-label="Select video quality"
					>
						<span class="flex items-center gap-2">
							<Monitor class="h-3 w-3" />
							<span class="text-xs font-semibold">{selectedQuality}</span>
						</span>
						<ChevronDown
							size={12}
							class="flex-shrink-0 opacity-70 transition-transform duration-300 {isExternalQualityMenuOpen
								? 'rotate-180'
								: ''}"
						/>
					</Button>
				</DropdownMenu.Trigger>
				<DropdownMenu.Content align="start" class="min-w-48">
					<DropdownMenu.Label class="flex items-center gap-2">
						<Monitor class="h-4 w-4" />
						Video Quality
					</DropdownMenu.Label>
					<DropdownMenu.Separator />

					{#each qualities as quality}
						<DropdownMenu.Item
							class="flex cursor-pointer items-center justify-between"
							onclick={() => switchQuality(quality)}
						>
							<span class="flex items-center gap-2">
								{quality.label}
								{#if quality.resolution}
									<span class="text-xs opacity-60">({quality.resolution})</span>
								{/if}
							</span>
							{#if selectedQuality === quality.label}
								<Check size={16} class="flex-shrink-0 text-green-500" />
							{/if}
						</DropdownMenu.Item>
					{/each}
				</DropdownMenu.Content>
			</DropdownMenu.Root>
		{/if}

		<!-- Picture-in-Picture Button -->
		{#if enablePiP}
			<Button
				variant="outline"
				size="sm"
				onclick={togglePictureInPicture}
				class="cursor-pointer"
				aria-label="Toggle Picture-in-Picture"
			>
				<PictureInPicture2 class="h-3 w-3" />
			</Button>
		{/if}
	</div>
</div>

<style>
	.player {
		width: 100%;
		aspect-ratio: 16 / 9;
		contain: layout;
		max-width: 100%;
		height: auto;
		border-radius: 8px;
		overflow: hidden;
	}

	:global(.compact-mode) .player {
		border-radius: 4px;
	}

	:global(.high-contrast) .player {
		border: 2px solid var(--border);
	}
</style>
