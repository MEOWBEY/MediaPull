<script lang="ts">
	import 'vidstack/player/styles/default/theme.css';
	import 'vidstack/player/styles/default/layouts/video.css';
	import 'vidstack/player';
	import 'vidstack/player/layouts/default';
	import 'vidstack/player/ui';

	import Check from 'lucide-svelte/icons/check';
	import ChevronDown from 'lucide-svelte/icons/chevron-down';
	import Monitor from 'lucide-svelte/icons/monitor';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu/index.js';
	import { Button } from '$lib/components/ui/button/index.js';

	let { src, poster = '', muted = false, preload = 'metadata', qualities = [] } = $props();

	let player: any = $state();
	let currentSrc = $state(src);
	let selectedQuality = $state('');
	let isExternalQualityMenuOpen = $state(false);
	let showErrorMessage = $state(false);

	// Initialize with first quality if available
	$effect(() => {
		if (qualities.length > 0) {
			const firstQuality = qualities[0];
			currentSrc = firstQuality.src;
			selectedQuality = firstQuality.label;
		}
	});

	function switchQuality(qualityOption: any) {
		if (!player || !qualityOption) return;

		currentSrc = qualityOption.src;
		selectedQuality = qualityOption.label;
		showErrorMessage = false;
		player.changeQuality(qualities.findIndex((q: any) => q.src === qualityOption.src));
	}

	function handleVideoError() {
		if (player) {
			player.pause();
		}
		showErrorMessage = true;
	}
</script>

<div class="flex w-full flex-col">
	<!-- Video Container -->
	<div class="video-container">
		<media-player
			bind:this={player}
			class="player"
			keep-alive
			playsinline
			src={currentSrc}
			{preload}
			view-type="video"
			crossorigin="anonymous"
			fullscreen-orientation="none"
			onerror={handleVideoError}
		>
			<media-provider>
				<media-poster src={poster}></media-poster>
			</media-provider>
			<media-video-layout></media-video-layout>
		</media-player>

		<!-- Error Message Overlay -->
		{#if showErrorMessage}
			<div class="absolute inset-0 z-50 flex items-center justify-center bg-black/80 p-4">
				<div class="w-full max-w-xs text-center text-white">
					<p class="text-sm">Failed to load</p>
				</div>
			</div>
		{/if}
	</div>

	<!-- Quality Selector -->
	{#if qualities.length > 1}
		<div class="flex items-center justify-start pt-3">
			<DropdownMenu.Root bind:open={isExternalQualityMenuOpen}>
				<DropdownMenu.Trigger>
					<Button
						variant="outline"
						size="sm"
						class="min-w-32 justify-between gap-2"
						aria-label="Select video quality"
					>
						<span class="flex items-center gap-2">
							<Monitor class="h-3 w-3" />
							<span class="text-xs font-medium">{selectedQuality}</span>
						</span>
						<ChevronDown
							size={12}
							class="flex-shrink-0 opacity-70 transition-transform duration-200 {isExternalQualityMenuOpen
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
		</div>
	{/if}
</div>

<style>
	.video-container {
		position: relative;
		width: 100%;
		aspect-ratio: 16 / 9;
		border-radius: 8px;
		overflow: hidden;
		transform: translateZ(0);
		backface-visibility: hidden;
	}

	.player {
		width: 100%;
		height: 100%;
		contain: layout style paint;
		max-width: 100%;
		position: relative;
		will-change: auto;
		transform: translateZ(0);
		-webkit-transform: translateZ(0);
	}
</style>
