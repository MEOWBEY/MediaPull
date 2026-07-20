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
		onGenerate?: () => void;
		generating?: boolean;
		progress?: number;
		stepLabel?: string;
		onCancel?: () => void;
		minWords?: number;
	} = $props();

	let filterQuery = $state('');
	let listEl = $state<HTMLDivElement | null>(null);

	function wordCount(text: string): number {
		const trimmed = text.trim();

		return trimmed ? trimmed.split(/\s+/).length : 0;
	}

	const visibleSegments = $derived(
		minWords > 0 ? segments.filter((seg) => wordCount(seg.text) >= minWords) : segments
	);

	const filteredSegments = $derived.by(() => {
		const q = filterQuery.trim().toLowerCase();

		if (!q) {
			return visibleSegments;
		}

		return visibleSegments.filter(
			(seg) => seg.text.toLowerCase().includes(q) || formatSecondsToTime(seg.start).includes(q)
		);
	});

	const activeSeg = $derived.by(() => {
		let candidate: SubtitleSegment | null = null;

		for (const seg of visibleSegments) {
			if (currentTime >= seg.start && currentTime <= seg.end) {
				return seg;
			}
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
		onOpenAutoFocus={(e) => e.preventDefault()}
		class="bg-background z-999999! flex w-full flex-col gap-0 overflow-hidden p-0 sm:max-w-lg {desktop.matches
			? ''
			: 'h-[65vh] rounded-t-2xl'}"
	>
		<Sheet.Header
			class="flex flex-row flex-nowrap items-start justify-between gap-3 px-4 pt-12  text-start sm:px-6"
		>
			<Sheet.Title class="font-heading flex min-w-0 shrink items-center gap-2 truncate text-xl font-bold sm:text-2xl">
				<Captions class="text-signal h-5 w-5 shrink-0 sm:h-6 sm:w-6" />
				<span class="truncate">{t('subtitles.panel.title')}</span>
			</Sheet.Title>
			{#if (segments.length && activeSeg) || canDownload}
				<div class="mt-0.5 flex shrink-0 flex-nowrap items-center gap-2">
					{#if canDownload}
						<Button
							variant="outline"
							size="sm"
							onclick={onDownload}
							class="h-9 shrink-0 gap-1.5 px-3"
							title={t('subtitles.download')}
							aria-label={t('subtitles.download')}
						>
							<Download class="h-4 w-4" />
							<span class="font-mono text-xs font-semibold">SRT</span>
						</Button>
					{/if}
					{#if segments.length && activeSeg}
						<Button
							variant="outline"
							size="sm"
							onclick={scrollToActive}
							class="h-9 shrink-0 gap-1.5 px-3"
							title={t('subtitles.panel.scrollToActive')}
							aria-label={t('subtitles.panel.scrollToActive')}
						>
							<LocateFixed class="h-4 w-4" />
							<span class="text-xs font-semibold">{t('subtitles.panel.jump')}</span>
						</Button>
					{/if}
				</div>
			{/if}
		</Sheet.Header>

		{#if segments.length}
			<div class="relative mt-2 shrink-0 px-4 sm:px-6">
				<Search
					class="text-muted-foreground pointer-events-none absolute top-1/2 inset-s-7 h-4 w-4 -translate-y-1/2 sm:inset-s-9"
				/>
				<input
					bind:value={filterQuery}
					type="search"
					placeholder={t('subtitles.panel.search')}
					aria-label={t('subtitles.panel.search')}
					class="bg-card/60 border-border/70 focus:ring-signal/40 h-10 w-full rounded-md border ps-9 pe-3 font-mono text-sm outline-none focus:ring-2"
				/>
			</div>

			<div
				bind:this={listEl}
				class="mt-3 min-h-0 flex-1 space-y-1 overflow-y-auto overscroll-contain px-4 pe-3 sm:px-6 sm:pe-5 contain-[paint] transform-[translateZ(0)]"
			>
				{#each filteredSegments as seg (seg)}
					<button
						type="button"
						data-active={seg === activeSeg}
						class="hover:bg-muted data-[active=true]:bg-signal/15 data-[active=true]:text-signal data-[active=true]:border-signal flex w-full cursor-pointer items-start gap-3 rounded-md border-s-2 border-transparent px-3 py-2 text-start transition-colors data-[active=true]:font-medium"
						onclick={() => onSeek(seg.start)}
					>
						<span
							class="text-muted-foreground shrink-0 pt-0.5 font-mono text-xs font-medium tabular-nums"
						>
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
						<div class="w-full max-w-xs space-y-2" role="status" aria-live="polite">
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
								class="gap-1.5"
								aria-label={t('subtitles.cancel')}
							>
								<X class="h-4 w-4" />
								{t('subtitles.cancel')}
							</Button>
						{/if}
					{:else}
						<Button size="sm" onclick={onGenerate} class="gap-1.5">
							<Captions class="h-4 w-4" />
							{t('subtitles.generate')}
						</Button>
					{/if}
				{/if}
			</div>
		{/if}
	</Sheet.Content>
</Sheet.Root>
