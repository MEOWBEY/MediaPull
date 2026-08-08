<script lang="ts">
	import Captions from '@lucide/svelte/icons/captions';
	import Loader2 from '@lucide/svelte/icons/loader-2';
	import X from '@lucide/svelte/icons/x';

	import { i18n } from '$lib/i18n/index.svelte';

	const { t } = i18n;

	let {
		running,
		resolving = false,
		hasTrack,
		stepLabel = '',
		progress = 0,
		showGenerate = true,
		onAction,
		onCancel
	}: {
		/** A subtitle job is in flight (spinner + label + % + cancel). */
		running: boolean;
		/** An existing track is being fetched/parsed (brief "Open" pill). */
		resolving?: boolean;
		/** A track already exists — the button becomes "Open". */
		hasTrack: boolean;
		stepLabel?: string;
		progress?: number;
		/** False hides the "Generate" affordance (e.g. a source with no audio
		 *  stream for Whisper to listen to). */
		showGenerate?: boolean;
		onAction: () => void;
		onCancel: () => void;
	} = $props();
</script>

<div class="flex w-full min-w-0 items-center gap-1.5 sm:w-auto sm:shrink">
	{#if running}
		<div
			class="border-border/70 flex w-full min-w-0 items-center overflow-hidden rounded-md border sm:w-auto"
		>
			<span
				class="text-muted-foreground inline-flex min-w-0 flex-1 items-center gap-1 px-2 py-1.5 font-mono text-xs sm:flex-none"
				title={stepLabel}
				role="status"
				aria-label={stepLabel}
			>
				<Loader2 class="h-3 w-3 shrink-0 animate-spin" />
				<span class="inline min-w-0 max-w-48 truncate text-xs">{stepLabel}</span>
				<span class="ms-auto tabular-nums sm:ms-0">{Math.round(progress * 100)}%</span>
			</span>
			<button
				type="button"
				onclick={onCancel}
				title={t('subtitles.cancel')}
				aria-label={t('subtitles.cancel')}
				class="border-border/70 text-muted-foreground hover:bg-muted hover:text-destructive flex shrink-0 items-center gap-1 border-s px-2 py-2 font-mono text-xs transition-colors sm:py-1.5"
			>
				<X class="h-3 w-3" />
				<span class="hidden sm:inline">{t('subtitles.cancel')}</span>
			</button>
		</div>
	{:else if resolving}
		<span
			class="border-border/70 text-muted-foreground animate-in fade-in flex w-full items-center justify-center gap-1.5 rounded-md border px-2.5 py-2 font-mono text-sm sm:w-auto sm:py-1.5"
		>
			<Loader2 class="h-3.5 w-3.5 animate-spin" />
			<span class="truncate">{t('subtitles.open')}</span>
		</span>
	{:else if hasTrack}
		<button
			type="button"
			onclick={onAction}
			title={t('subtitles.openHint')}
			class="border-signal/40 bg-signal/15 text-signal animate-in fade-in flex w-full min-w-0 items-center justify-center gap-1.5 rounded-md border px-2.5 py-2 font-mono text-sm font-semibold transition-colors hover:bg-signal/25 sm:w-auto sm:justify-start sm:py-1.5"
		>
			<Captions class="h-3.5 w-3.5 shrink-0" />
			<span class="truncate">{t('subtitles.open')}</span>
		</button>
	{:else if showGenerate}
		<button
			type="button"
			onclick={onAction}
			title={t('subtitles.generateHint')}
			class="border-border/70 text-muted-foreground hover:bg-muted hover:text-foreground animate-in fade-in flex w-full min-w-0 items-center justify-center gap-1.5 rounded-md border px-2.5 py-2 font-mono text-sm transition-colors sm:w-auto sm:justify-start sm:py-1.5"
		>
			<Captions class="h-3.5 w-3.5 shrink-0" />
			<span class="truncate">{t('subtitles.generate')}</span>
		</button>
	{/if}
</div>
