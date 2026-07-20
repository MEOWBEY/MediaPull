<script lang="ts">
	import PlayCircle from '@lucide/svelte/icons/circle-play';
	import ClipboardPaste from '@lucide/svelte/icons/clipboard-paste';
	import Download from '@lucide/svelte/icons/download';
	import Sparkles from '@lucide/svelte/icons/sparkles';

	import { i18n } from '$lib/i18n/index.svelte';

	let { nested = false }: { nested?: boolean } = $props();

	const { t } = i18n;

	// Build reactively so the labels re-translate when the locale changes.
	const steps = $derived([
		{ icon: ClipboardPaste, title: t('how.step1.title'), body: t('how.step1.body') },
		{ icon: Sparkles, title: t('how.step2.title'), body: t('how.step2.body') },
		{ icon: PlayCircle, title: t('how.step3.title'), body: t('how.step3.body') },
		{ icon: Download, title: t('how.step4.title'), body: t('how.step4.body') }
	]);
</script>

<section class={nested ? 'space-y-6' : 'mt-12 space-y-6'}>
	{#if !nested}
		<div>
			<p class="text-muted-foreground font-mono text-xs tracking-widest uppercase">
				<span class="text-signal">//</span>
				{t('how.heading')}
			</p>
			<p class="text-muted-foreground mt-1 text-sm">
				{t('how.subtitle')}
			</p>
		</div>
	{/if}

	<!-- Genuine sequence (paste → detect → preview → download), so numbered mono
	     markers carry real meaning. Card surface with hairline dividers. -->
	<ol class="border-border/70 bg-card grid overflow-hidden rounded-lg border sm:grid-cols-2 lg:grid-cols-4">
		{#each steps as step, i (i)}
			<li
				class="border-border/70 flex flex-col gap-2 p-4 [&:not(:last-child)]:border-b sm:[&:not(:last-child)]:border-e lg:[&:not(:last-child)]:border-b-0"
			>
				<div class="flex items-center gap-2">
					<span class="text-signal font-mono text-xs font-bold tabular-nums">
						{String(i + 1).padStart(2, '0')}
					</span>
					<step.icon class="text-muted-foreground h-4 w-4" />
				</div>
				<h3 class="text-sm font-semibold">{step.title}</h3>
				<p class="text-muted-foreground text-xs leading-relaxed">{step.body}</p>
			</li>
		{/each}
	</ol>
</section>
