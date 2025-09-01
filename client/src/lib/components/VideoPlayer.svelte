<script lang="ts">
	import 'vidstack/player/styles/default/theme.css';
	import 'vidstack/player/styles/default/layouts/video.css';
	import 'vidstack/player';
	import 'vidstack/player/layouts/default';
	import 'vidstack/player/ui';

	import Check from 'lucide-svelte/icons/check';
	import Play from 'lucide-svelte/icons/play';
	import ChevronDown from 'lucide-svelte/icons/chevron-down';
	import { appStore } from '$lib/stores/app-state.svelte';

	let { poster = '', qualities = [] } = $props();

	let preferences = $derived(appStore.preferences);

	let player: any = $state();
	let currentSrc = $state('');
	let selectedQualityResolution = $state(qualities[0]?.resolution);
	let isQualitySheetOpen = $state(false);
	let isPlayerHasError = $state(false);
	let isAutoplayBlocked = $state(false);
	let isControlsVisible = $state(false);
	let isFullscreen = $state(false);

	/* Watch for controls visibility and fullscreen changes (preserved) */
	$effect(() => {
		if (!player) return;

		const updateControlsVisibility = () => {
			try {
				const mediaState = player.state;
				if (mediaState) {
					isControlsVisible = mediaState.isControlsVisible || false;
				}
			} catch (e) {
				console.warn('Error reading controls visibility:', e);
			}
		};

		const updateFullscreenState = () => {
			try {
				const mediaState = player.state;
				if (mediaState) {
					isFullscreen = mediaState.fullscreen || false;
				}
			} catch (e) {
				console.warn('Error reading fullscreen state:', e);
			}
		};

		const unsubscribe = player.subscribe?.((state: any) => {
			if (state && 'isControlsVisible' in state) {
				isControlsVisible = state.isControlsVisible;
			}
			if (state && 'fullscreen' in state) {
				isFullscreen = state.fullscreen;
			}
		});

		const events = ['controls-change', 'user-idle-change', 'pointer-enter', 'pointer-leave'];
		const fullscreenEvents = ['fullscreen-change', 'fullscreen-error'];

		events.forEach((event) => player.addEventListener?.(event, updateControlsVisibility));
		fullscreenEvents.forEach((event) => player.addEventListener?.(event, updateFullscreenState));

		// Initial checks
		updateControlsVisibility();
		updateFullscreenState();

		return () => {
			unsubscribe?.();
			events.forEach((event) => player.removeEventListener?.(event, updateControlsVisibility));
			fullscreenEvents.forEach((event) =>
				player.removeEventListener?.(event, updateFullscreenState)
			);
		};
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

			try {
				player.addEventListener?.('can-play', onCanPlay);
				player.addEventListener?.('error', onError);
			} catch (e) {
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

	async function initiatePlayback() {
		if (!player) return;

		isPlayerHasError = false;
		isAutoplayBlocked = false;

		if (!currentSrc && qualities.length > 0) {
			currentSrc = preferences.enableProxyForVideoExtract
				? qualities[0].proxiedVideoUrl
				: qualities[0].sourceVideoUrl;
			selectedQualityResolution = qualities[0].resolution;
		}
		player.startLoading?.();

		const ready = await waitForCanPlay(8000);
		if (!ready) {
			console.warn('Timed out waiting for can-play; media may not be ready yet.');
		}

		try {
			await player.play();
			player.muted = preferences.enableVideoMute;
			isAutoplayBlocked = false;
			isPlayerHasError = false;
			console.debug('Playback started successfully');
		} catch (err: any) {
			console.warn('Autoplay/play() rejected:', err);
			isAutoplayBlocked = true;
		}
	}

	async function switchQuality(option: any) {
		if (!player || !option) return;

		const wasPlaying = !player.paused;
		const currentTime = player.currentTime ?? 0;

		currentSrc = preferences.enableProxyForVideoExtract
			? option.proxiedVideoUrl
			: option.sourceVideoUrl;
		selectedQualityResolution = option.resolution;
		isPlayerHasError = false;
		isAutoplayBlocked = false;
		isQualitySheetOpen = false;

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
				isAutoplayBlocked = true;
			}
		}
	}

	function handleVideoError() {
		if (player) player.pause?.();
		isPlayerHasError = true;
		isAutoplayBlocked = false;
	}
</script>

<div class="video-container relative aspect-video w-full overflow-hidden">
	<media-player
		bind:this={player}
		src={currentSrc}
		onerror={handleVideoError}
		load={initiatePlayback}
		poster-load="idle"
		muted={preferences.enableVideoMute}
		preload={preferences.enableVideoPreloadMetadata ? 'metadata' : 'none'}
		view-type="video"
		fullscreen-orientation="none"
		crossorigin="anonymous"
		keep-alive
		playsinline
		class="player h-full w-full max-w-full will-change-auto"
	>
		<media-provider>
			{#if preferences.showVideoThumbnail}
				<media-poster src={poster} poster-load="idle"></media-poster>
			{/if}
		</media-provider>
		<media-video-layout></media-video-layout>

		{#if qualities.length > 1 && (isControlsVisible || !isAutoplayBlocked || isPlayerHasError)}
			<div class="absolute top-1.5 left-1.5 !z-50">
				<button
					class={`flex cursor-pointer items-center justify-between gap-1 rounded-lg border border-zinc-700 bg-zinc-900/50 px-3 py-1 
          text-sm font-semibold text-white transition
          hover:bg-zinc-800`}
					aria-expanded={isQualitySheetOpen}
					aria-label="Video Quality Settings"
					onclick={() => (isQualitySheetOpen = !isQualitySheetOpen)}
					data-fullscreen={isFullscreen}
				>
					{selectedQualityResolution}p
					<ChevronDown class="h-4 w-4 shrink-0" />
				</button>
			</div>
		{/if}

		<!-- Loading State with Play Button -->
		{#if !currentSrc || isAutoplayBlocked}
			<div class="absolute inset-0 z-40 flex items-center justify-center">
				<button
					class="flex h-12 w-12 cursor-pointer items-center justify-center rounded-full bg-white p-4 text-black transition-transform duration-200 hover:scale-105 md:h-14 md:w-14 md:p-6"
					aria-label="Play video"
					onclick={() => initiatePlayback()}
				>
					<Play size={24} class="shrink-0" />
				</button>
			</div>
		{/if}
		<!-- Quality Sheet -->
		{#if isQualitySheetOpen}
			<!-- Backdrop -->
			<div
				class={'fixed inset-0 cursor-pointer'}
				onclick={() => (isQualitySheetOpen = false)}
				aria-hidden={!isQualitySheetOpen}
			></div>

			<!-- Sheet -->
			<div
				class={'fixed bottom-5 left-1/2 !z-[999999] mx-auto w-full max-w-xl -translate-x-1/2 rounded-lg border border-zinc-700 bg-zinc-900 p-2 text-white shadow-lg transition-all duration-200  md:max-w-6xl' +
					(isQualitySheetOpen ? 'translate-y-0 opacity-100' : 'translate-y-full opacity-0')}
				role="dialog"
				aria-modal="true"
				aria-label="Video Quality"
				data-open={isQualitySheetOpen}
				data-fullscreen={isFullscreen}
				aria-hidden={!isQualitySheetOpen}
			>
				<header class="flex items-center justify-between gap-2 px-3 py-2">
					<div class="flex items-center gap-2 text-base font-semibold">
						<span>Video Quality</span>
					</div>
				</header>

				<div class="flex flex-col gap-2 px-2 pb-3">
					{#each qualities as quality, i}
						<button
							data-quality-option
							data-selected={selectedQualityResolution === quality.resolution}
							onclick={() => {
								switchQuality(quality);
								isQualitySheetOpen = false;
							}}
							class="flex w-full cursor-pointer items-center justify-between rounded-md px-2 py-2 text-left text-sm hover:bg-white/10"
							tabindex="0"
						>
							<span>{quality.resolution}p</span>
							{#if selectedQualityResolution === quality.resolution}
								<Check class="h-5 w-5 text-green-500" />
							{/if}
						</button>
					{/each}
				</div>
			</div>
		{/if}

		<!-- Error Message Overlay -->
		{#if isPlayerHasError}
			<div class="absolute inset-0 !z-49 flex items-center justify-center bg-black/80 p-4">
				<div class="w-full max-w-44 rounded-lg bg-zinc-800 p-4 text-center text-white">
					<p class="text-sm text-red-500 md:text-base">
						Failed to load Change quality or refresh page
					</p>
				</div>
			</div>
		{/if}
	</media-player>
</div>

<style>
	/* Hide Google Cast button to replace with quality button */
	:global(.vds-google-cast-button) {
		display: none !important;
	}
</style>
