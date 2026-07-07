<script lang="ts">
	import Captions from '@lucide/svelte/icons/captions';
	import Download from '@lucide/svelte/icons/download';
	import Loader2 from '@lucide/svelte/icons/loader-2';
	import Search from '@lucide/svelte/icons/search';

	import { Button } from '$lib/components/ui/button';
	import * as Sheet from '$lib/components/ui/sheet';
	import { formatSecondsToTime } from '$lib/format';
	import { i18n } from '$lib/i18n/index.svelte';
	import type { SubtitleSegment } from '$lib/types';
	import { MediaQuery } from '$lib/viewport.svelte';

	const { t } = i18n;

	// Side sheet on desktop (room beside the video), bottom sheet on mobile
	// (the video stays visible above it while scrubbing captions).
	const desktop = new MediaQuery('(min-width: 640px)');

	let {
		open = $bindable(),
		segments,
		currentTime,
		onSeek,
		canDownload = false,
		onDownload,
		onGenerate,
		generating = false
	}: {
		open: boolean;
		segments: SubtitleSegment[];
		currentTime: number;
		onSeek: (time: number) => void;
		canDownload?: boolean;
		onDownload?: () => void;
		/** Lets the empty state kick off generation right away, instead of
		 *  closing the panel and hunting for the card's own Subtitles button. */
		onGenerate?: () => void;
		generating?: boolean;
	} = $props();

	let filterQuery = $state('');
	const rowEls: Record<number, HTMLButtonElement> = {};

	// Filter by text OR timestamp — typing "1:23" jumps you to lines around
	// that time, typing words filters by content.
	const filteredSegments = $derived.by(() => {
		const q = filterQuery.trim().toLowerCase();

		if (!q) {return segments;}

		return segments.filter(
			(seg) => seg.text.toLowerCase().includes(q) || formatSecondsToTime(seg.start).includes(q)
		);
	});

	// The segment currently under the playhead (highlighted + auto-scrolled).
	const activeSeg = $derived(
		segments.find((seg) => currentTime >= seg.start && currentTime <= seg.end) ?? null
	);

	$effect(() => {
		if (!open || !activeSeg) {return;}

		const idx = filteredSegments.indexOf(activeSeg);

		if (idx >= 0) {rowEls[idx]?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });}
	});
</script>

<Sheet.Root bind:open>
	<Sheet.Content
		side={desktop.matches ? 'right' : 'bottom'}
		class="bg-background z-999999! flex w-full flex-col gap-0 overflow-hidden p-4 sm:max-w-md sm:p-6 {desktop.matches
			? ''
			: 'h-[65vh] rounded-t-3xl'}"
	>
		<Sheet.Header class="flex-row items-center justify-between px-0 text-start">
			<Sheet.Title class="ds-gradient-text text-xl font-bold sm:text-2xl">
				{t('subtitles.panel.title')}
			</Sheet.Title>
			{#if canDownload}
				<Button
					variant="outline"
					size="icon"
					onclick={onDownload}
					class="h-9 w-9 shrink-0"
					title={t('subtitles.download')}
				>
					<Download class="h-4 w-4" />
				</Button>
			{/if}
		</Sheet.Header>

		{#if segments.length}
			<div class="relative mt-3 shrink-0">
				<Search
					class="text-muted-foreground pointer-events-none absolute top-1/2 inset-s-3 h-4 w-4 -translate-y-1/2"
				/>
				<input
					bind:value={filterQuery}
					type="search"
					placeholder={t('subtitles.panel.search')}
					aria-label={t('subtitles.panel.search')}
					class="bg-card/60 border-border/60 focus:ring-primary/40 h-10 w-full rounded-full border ps-9 pe-3 text-sm outline-none focus:ring-2"
				/>
			</div>

			<div class="mt-3 min-h-0 flex-1 space-y-1 overflow-y-auto pe-1">
				{#each filteredSegments as seg, i (seg)}
					<button
						bind:this={rowEls[i]}
						type="button"
						data-active={seg === activeSeg}
						class="hover:bg-muted data-[active=true]:bg-primary/10 data-[active=true]:text-primary flex w-full items-start gap-3 rounded-lg px-3 py-2 text-start transition-colors"
						onclick={() => onSeek(seg.start)}
					>
						<span class="text-muted-foreground shrink-0 pt-0.5 text-xs font-medium tabular-nums">
							{formatSecondsToTime(seg.start)}
						</span>
						<span class="text-sm leading-snug">{seg.text}</span>
					</button>
				{:else}
					<p class="text-muted-foreground py-8 text-center text-sm">
						{t('subtitles.panel.empty')}
					</p>
				{/each}
			</div>
		{:else}
			<div class="mt-6 flex flex-col items-center gap-4 text-center">
				<p class="text-muted-foreground text-sm">
					{t('subtitles.panel.noTrack')}
				</p>
				{#if onGenerate}
					<Button size="sm" disabled={generating} onclick={onGenerate} class="gap-1.5 rounded-full">
						{#if generating}
							<Loader2 class="h-4 w-4 animate-spin" />
							{t('subtitles.generating')}
						{:else}
							<Captions class="h-4 w-4" />
							{t('subtitles.generate')}
						{/if}
					</Button>
				{/if}
			</div>
		{/if}
	</Sheet.Content>
</Sheet.Root>
