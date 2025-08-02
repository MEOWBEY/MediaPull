<script lang="ts">
	import 'vidstack/player/styles/default/theme.css';
	import 'vidstack/player/styles/default/layouts/video.css';

	import 'vidstack/player';
	import 'vidstack/player/layouts/default';
	import 'vidstack/player/ui';

	let {
		src,
		poster = '',
		autoplay = false,
		muted = false,
		preload = 'metadata' as const,
		load = 'visible' as const
	} = $props();

	let player: any = $state();

	function onError(event: any) {
		console.error('Video error:', event.detail);
	}
</script>

<media-player
	bind:this={player}
	keep-alive
	playsInline
	class="player"
	{src}
	{preload}
	{load}
	viewType="video"
	{autoplay}
	{muted}
	onerror={onError}
	crossorigin="anonymous"
>
	<media-provider>
		<media-poster src={poster}> </media-poster>
	</media-provider>

	<media-video-layout></media-video-layout>
</media-player>

<style>
	.player {
		width: 100%;
		aspect-ratio: 16 / 9;
		background-color: #000;
		contain: layout;
		max-width: 100%;
		height: auto;
	}
	.player {
		--media-tooltip-y-offset: 30px;
		--media-menu-y-offset: 30px;
	}
</style>
