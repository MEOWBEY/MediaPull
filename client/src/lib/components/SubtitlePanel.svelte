<script lang="ts">
	import Captions from '@lucide/svelte/icons/captions';
	import Download from '@lucide/svelte/icons/download';
	import Loader2 from '@lucide/svelte/icons/loader-2';
	import LocateFixed from '@lucide/svelte/icons/locate-fixed';
	import Search from '@lucide/svelte/icons/search';
	import X from '@lucide/svelte/icons/x';

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
		generating = false,
		progress = 0,
		stepLabel = '',
		onCancel,
		minWords = 0
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
		/** Real job progress (0..1) and the pipeline stage it's in -- shown
		 *  while `generating` so the user sees actual movement, not a spinner. */
		progress?: number;
		stepLabel?: string;
		/** Stops an in-flight Groq job -- shown next to the generating spinner. */
		onCancel?: () => void;
		/** Hide lines shorter than this many words from the panel only (the
		 *  video's own captions are untouched). 0 = show every line. */
		minWords?: number;
	} = $props();

	let filterQuery = $state('');
	// The scroll container -- the "scroll to current line" button reaches into
	// it to bring the highlighted row into view on demand.
	let listEl = $state<HTMLDivElement | null>(null);

	// No *automatic* scroll on purpose: the list never moves on its own while
	// playing (clicks/taps used to trigger surprise jumps). The active line is
	// only highlighted -- but a header button now lets the user jump to it when
	// they want, see `scrollToActive`.

	function wordCount(text: string): number {
		const trimmed = text.trim();

		return trimmed ? trimmed.split(/\s+/).length : 0;
	}

	// Short-line filter: applied to the panel list ONLY. The video keeps every
	// cue (it renders from the VTT track, not from this list), so single-word
	// lines like "Justin" still show on the player -- just not here.
	const visibleSegments = $derived(
		minWords > 0 ? segments.filter((seg) => wordCount(seg.text) >= minWords) : segments
	);

	// Filter by text OR timestamp — typing "1:23" jumps you to lines around
	// that time, typing words filters by content.
	const filteredSegments = $derived.by(() => {
		const q = filterQuery.trim().toLowerCase();

		if (!q) {
			return visibleSegments;
		}

		return visibleSegments.filter(
			(seg) => seg.text.toLowerCase().includes(q) || formatSecondsToTime(seg.start).includes(q)
		);
	});

	// The segment currently under the playhead. During a silence gap (no cue
	// spans `currentTime`) we keep the most recent line that has already started
	// highlighted, instead of clearing it -- otherwise the green highlight
	// flickers off every time the speaker pauses. Computed over the *visible*
	// list so the highlighted row is always one that's actually shown.
	const activeSeg = $derived.by(() => {
		let candidate: SubtitleSegment | null = null;

		for (const seg of visibleSegments) {
			if (currentTime >= seg.start && currentTime <= seg.end) {
				return seg;
			}
			// Segments are ordered by start time: once one starts in the future,
			// no later one can be active or the current gap-fallback candidate.
			if (seg.start > currentTime) {
				break;
			}
			candidate = seg;
		}

		return candidate;
	});

	function scrollToActive() {
		const el = listEl?.querySelector<HTMLElement>('[data-active="true"]');

		el?.scrollIntoView({ block: 'center', behavior: 'smooth' });
	}
</script>

<Sheet.Root bind:open>
	<Sheet.Content
		side={desktop.matches ? 'right' : 'bottom'}
		closeLabel={t('common.close')}
		hideClose
		class="bg-background z-999999! flex w-full flex-col gap-0 overflow-hidden p-4 sm:max-w-md sm:p-6 {desktop.matches
			? ''
			: 'h-[65vh] rounded-t-3xl'}"
	>
		<Sheet.Header class="flex-row items-center justify-between px-0 text-start">
			<Sheet.Title class="ds-gradient-text text-xl font-bold sm:text-2xl">
				{t('subtitles.panel.title')}
			</Sheet.Title>
			<div class="flex shrink-0 items-center gap-2">
				{#if segments.length && activeSeg}
					<Button
						variant="outline"
						size="icon"
						onclick={scrollToActive}
						class="h-9 w-9 shrink-0"
						title={t('subtitles.panel.scrollToActive')}
						aria-label={t('subtitles.panel.scrollToActive')}
					>
						<LocateFixed class="h-4 w-4" />
					</Button>
				{/if}
				{#if canDownload}
					<Button
						variant="outline"
						size="icon"
						onclick={onDownload}
						class="h-9 w-9 shrink-0"
						title={t('subtitles.download')}
						aria-label={t('subtitles.download')}
					>
						<Download class="h-4 w-4" />
					</Button>
				{/if}
			</div>
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

			<!-- GPU-promote the scroller (translateZ) and contain its paint so the
			     row text doesn't rasterize blank-then-late during momentum scroll
			     on mobile -- the browser keeps the painted layer instead of
			     re-painting each frame. `overscroll-contain` stops the gesture
			     from chaining to the page behind the sheet. -->
			<div
				bind:this={listEl}
				class="mt-3 min-h-0 flex-1 space-y-1 overflow-y-auto overscroll-contain pe-1 [contain:paint] [transform:translateZ(0)]"
			>
				{#each filteredSegments as seg (seg)}
					<button
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
					{#if generating}
						<!-- Progress is status, not a button: a bar + percentage + the
						     pipeline stage, with cancel as its own explicit action. -->
						<div class="w-full max-w-xs space-y-2">
							<div class="bg-muted h-1.5 w-full overflow-hidden rounded-full">
								<div
									class="bg-primary h-full rounded-full transition-[width] duration-300"
									style="width: {Math.round(progress * 100)}%"
								></div>
							</div>
							<div class="text-muted-foreground flex items-center justify-between gap-2 text-xs">
								<span class="inline-flex min-w-0 items-center gap-1.5">
									<Loader2 class="h-3.5 w-3.5 shrink-0 animate-spin" />
									<span class="truncate">{stepLabel || t('subtitles.generating')}</span>
								</span>
								<span class="shrink-0 tabular-nums">{Math.round(progress * 100)}%</span>
							</div>
						</div>
						{#if onCancel}
							<Button
								variant="outline"
								size="sm"
								onclick={onCancel}
								class="gap-1.5 rounded-full"
								aria-label={t('subtitles.cancel')}
							>
								<X class="h-4 w-4" />
								{t('subtitles.cancel')}
							</Button>
						{/if}
					{:else}
						<Button size="sm" onclick={onGenerate} class="gap-1.5 rounded-full">
							<Captions class="h-4 w-4" />
							{t('subtitles.generate')}
						</Button>
					{/if}
				{/if}
			</div>
		{/if}
	</Sheet.Content>
</Sheet.Root>
