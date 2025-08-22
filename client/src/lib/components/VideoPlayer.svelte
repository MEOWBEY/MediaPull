<script lang="ts">
	import 'vidstack/player/styles/default/theme.css';
	import 'vidstack/player/styles/default/layouts/video.css';
	import 'vidstack/player';
	import 'vidstack/player/layouts/default';
	import 'vidstack/player/ui';

	import Check from 'lucide-svelte/icons/check';
	import ChevronDown from 'lucide-svelte/icons/chevron-down';
	import Monitor from 'lucide-svelte/icons/monitor';
	import Play from 'lucide-svelte/icons/play';

	import * as DropdownMenu from '$lib/components/ui/dropdown-menu/index.js';
	import { Button } from '$lib/components/ui/button/index.js';

	let { poster = '', preload = 'none', muted = false, qualities = [] } = $props();
	let player: any = $state();
	let currentSrc = $state('');
	let selectedQuality = $state('');
	let isExternalQualityMenuOpen = $state(false);
	let showErrorMessage = $state(false);
	let autoplayAfterLoadingFailed = $state(false);

	$effect(() => {
		if (qualities.length > 0) {
			selectedQuality = qualities[0].label;
		}
	});

	function waitForCanPlay(timeout = 7000) {
		return new Promise((resolve) => {
			if (!player) return resolve(false);

			let resolved = false;
			const onCanPlay = () => {
				if (resolved) return;
				resolved = true;
				cleanup();
				resolve(true);
			};

			const onError = () => {
				if (resolved) return;
				resolved = true;
				cleanup();
				resolve(false);
			};

			const cleanup = () => {
				try {
					player.removeEventListener?.('can-play', onCanPlay);
					player.removeEventListener?.('error', onError);
				} catch {}
				clearTimeout(timer);
			};

			// Bind to vidstack event name `can-play`
			try {
				player.addEventListener?.('can-play', onCanPlay);
				player.addEventListener?.('error', onError);
			} catch (e) {
				// if addEventListener is not available, resolve false immediately
				cleanup();
				return resolve(false);
			}

			const timer = setTimeout(() => {
				if (resolved) return;
				resolved = true;
				cleanup();
				resolve(false);
			}, timeout);
		});
	}

	async function startPlayback() {
		if (!player) return;

		showErrorMessage = false;
		autoplayAfterLoadingFailed = false;

		if (!currentSrc && qualities.length > 0) {
			currentSrc = qualities[0].src;
			selectedQuality = qualities[0].label;
		}
		player.startLoading?.();

		const ready = await waitForCanPlay(8000);
		if (!ready) {
			console.warn('Timed out waiting for can-play; media may not be ready yet.');
		}

		try {
			await player.play();
			player.muted = muted;
			autoplayAfterLoadingFailed = false;
			showErrorMessage = false;
			console.debug('Playback started successfully');
		} catch (err: any) {
			console.warn('Autoplay/play() rejected:', err);
			autoplayAfterLoadingFailed = true;
		}
	}

	async function switchQuality(option: any) {
		if (!player || !option) return;

		const wasPlaying = !player.paused;
		const currentTime = player.currentTime ?? 0;

		currentSrc = option.src;
		selectedQuality = option.label;
		showErrorMessage = false;
		autoplayAfterLoadingFailed = false;

		player.startLoading?.();

		const ready = await waitForCanPlay(8000);
		if (!ready) {
			console.warn('Timed out waiting for can-play after quality switch');
		}

		player.currentTime = currentTime;
		if (wasPlaying) {
			try {
				await player.play();
			} catch (e) {
				console.warn('play after quality switch failed', e);
				autoplayAfterLoadingFailed = true;
			}
		}
	}

	function handleVideoError() {
		if (player) player.pause?.();
		showErrorMessage = true;
		autoplayAfterLoadingFailed = false;
	}
</script>

<div class="flex w-full flex-col">
	<!-- Video Container -->
	<div class="video-container relative aspect-video w-full overflow-hidden rounded-lg">
		<media-player
			bind:this={player}
			src={currentSrc}
			onerror={handleVideoError}
			load={startPlayback}
			posterLoad="play"
			{muted}
			{preload}
			keep-alive
			playsinline
			view-type="video"
			crossorigin="anonymous"
			fullscreen-orientation="none"
			class="player relative h-full w-full max-w-full will-change-auto"
		>
			<media-provider>
				<media-poster src={poster}></media-poster>
			</media-provider>
			<media-video-layout></media-video-layout>
		</media-player>

		{#if !currentSrc || autoplayAfterLoadingFailed}
			<div class="absolute inset-0 z-40 flex items-center justify-center">
				<button
					class="flex h-12 w-12 cursor-pointer items-center justify-center rounded-full bg-white p-4 text-black transition-transform duration-200 hover:scale-105 md:h-14 md:w-14 md:p-6"
					aria-label="Play video"
					onclick={() => startPlayback()}
				>
					<Play size={24} class="shrink-0" />
				</button>
			</div>
		{/if}

		<!-- Error Message -->
		{#if showErrorMessage}
			<div class="absolute inset-0 z-50 flex items-center justify-center bg-black/80 p-4">
				<div class="w-full max-w-xs text-center text-white">
					<p class="text-sm md:text-base">Failed to load</p>
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
							</span>
							{#if selectedQuality === quality.resolution}
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
		transform: translateZ(0);
		backface-visibility: hidden;
	}

	.player {
		contain: layout style paint;
		will-change: auto;
		transform: translateZ(0);
		-webkit-transform: translateZ(0);
	}
</style>
