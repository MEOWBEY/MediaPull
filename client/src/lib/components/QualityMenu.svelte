<script lang="ts">
	import Check from '@lucide/svelte/icons/check';
	import SlidersHorizontal from '@lucide/svelte/icons/sliders-horizontal';

	import { qualityLabel } from '$lib/format';
	import type { VideoFormat } from '$lib/types';

	// The video-player's quality picker -- slotted into the skin so it overlays
	// correctly (including in fullscreen). Split out of VideoPlayer since it's
	// a self-contained trigger+menu with its own open/close and outside-click
	// handling, unrelated to media playback itself.
	let {
		qualities,
		activeIndex,
		switching,
		onSwitch,
		controlsVisible
	}: {
		qualities: Partial<VideoFormat>[];
		activeIndex: number;
		switching: boolean;
		onSwitch: (index: number) => void;
		/** Follows the skin's own control-bar visibility so this fades in/out
		 *  together with the rest of the controls. */
		controlsVisible: boolean;
	} = $props();

	let qualityRoot: HTMLElement | null = $state(null);
	let menuOpen = $state(false);

	// Close the menu when clicking anywhere outside it (the trigger itself
	// still toggles via its own onclick — it lives inside qualityRoot, so this
	// outside-handler ignores it).
	$effect(() => {
		if (!menuOpen) {
			return;
		}

		const onDocPointerDown = (event: Event) => {
			if (qualityRoot && !qualityRoot.contains(event.target as Node)) {
				menuOpen = false;
			}
		};

		document.addEventListener('pointerdown', onDocPointerDown);

		return () => document.removeEventListener('pointerdown', onDocPointerDown);
	});

	function switchTo(index: number) {
		menuOpen = false;
		onSwitch(index);
	}
</script>

<div
	bind:this={qualityRoot}
	class="ds-quality"
	data-open={menuOpen}
	data-visible={controlsVisible || menuOpen}
>
	<button
		type="button"
		class="ds-quality__trigger"
		aria-haspopup="menu"
		aria-expanded={menuOpen}
		aria-busy={switching}
		disabled={switching}
		onclick={() => (menuOpen = !menuOpen)}
	>
		<!-- While switching, the sliders icon pulses (opacity only) instead of
		     spinning: a non-circular glyph spinning reads as broken, whereas a soft
		     pulse clearly says "working" without the jarring rotation or a recolor. -->
		<SlidersHorizontal class="h-3.5 w-3.5 {switching ? 'animate-pulse' : ''}" />
		<span>{qualityLabel(qualities[activeIndex], activeIndex)}</span>
	</button>

	{#if menuOpen}
		<div class="ds-quality__menu" role="menu">
			{#each qualities as q, i (i)}
				<button
					type="button"
					role="menuitemradio"
					aria-checked={i === activeIndex}
					disabled={switching}
					class="ds-quality__item disabled:cursor-wait disabled:opacity-60"
					data-active={i === activeIndex}
					onclick={() => switchTo(i)}
				>
					<span>{qualityLabel(q, i)}</span>
					{#if i === activeIndex}
						<Check class="h-3.5 w-3.5" />
					{/if}
				</button>
			{/each}
		</div>
	{/if}
</div>
