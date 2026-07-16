<script lang="ts">
	import PlayCircle from '@lucide/svelte/icons/circle-play';
	import ClipboardPaste from '@lucide/svelte/icons/clipboard-paste';
	import Download from '@lucide/svelte/icons/download';
	import MonitorSmartphone from '@lucide/svelte/icons/monitor-smartphone';
	import Sparkles from '@lucide/svelte/icons/sparkles';
	import Waypoints from '@lucide/svelte/icons/waypoints';

	import { i18n } from '$lib/i18n/index.svelte';
	import type { Preferences } from '$lib/types';

	let {
		preferences,
		nested = false
	}: { preferences: Pick<Preferences, 'enableCompact'>; nested?: boolean } = $props();

	const { t } = i18n;

	// Build reactively so the labels re-translate when the locale changes.
	const steps = $derived([
		{ icon: ClipboardPaste, title: t('how.step1.title'), body: t('how.step1.body') },
		{ icon: Sparkles, title: t('how.step2.title'), body: t('how.step2.body') },
		{ icon: PlayCircle, title: t('how.step3.title'), body: t('how.step3.body') },
		{ icon: Download, title: t('how.step4.title'), body: t('how.step4.body') }
	]);

	const features = $derived([
		{ icon: Waypoints, title: t('how.feat1.title'), body: t('how.feat1.body') },
		{ icon: MonitorSmartphone, title: t('how.feat2.title'), body: t('how.feat2.body') }
	]);
</script>

<section class={nested ? (preferences.enableCompact ? 'space-y-4' : 'space-y-6') : `mt-12 ${preferences.enableCompact ? 'space-y-4' : 'space-y-6'}`}>
	{#if !nested}
		<div class="text-center">
			<h2 class="text-xl font-bold tracking-tight">{t('how.heading')}</h2>
			<p class="text-muted-foreground mt-1 text-sm">
				{t('how.subtitle')}
			</p>
		</div>
	{/if}

	<ol class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
		{#each steps as step, i (i)}
			<li
				class="ds-glass shadow-soft relative p-4 {i % 2 === 0 ? 'rounded-3xl' : 'rounded-[1.9rem]'}"
			>
				<span
					class="bg-primary text-primary-foreground absolute -top-2.5 -inset-s-2.5 flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold shadow-sm"
				>
					{i + 1}
				</span>
				<step.icon class="text-aurora-1 mb-2 h-5 w-5" />
				<h3 class="text-sm font-semibold">{step.title}</h3>
				<p class="text-muted-foreground mt-1 text-xs leading-relaxed">{step.body}</p>
			</li>
		{/each}
	</ol>

	<div class="grid gap-3 sm:grid-cols-2">
		{#each features as feature, i (i)}
			<div class="ds-glass shadow-soft flex items-start gap-3 rounded-[1.9rem] p-4">
				<span
					class="bg-secondary/15 text-secondary flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl"
				>
					<feature.icon class="h-5 w-5" />
				</span>
				<div>
					<h3 class="text-sm font-semibold">{feature.title}</h3>
					<p class="text-muted-foreground mt-1 text-xs leading-relaxed">{feature.body}</p>
				</div>
			</div>
		{/each}
	</div>
</section>
