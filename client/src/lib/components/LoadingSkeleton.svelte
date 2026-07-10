<script lang="ts">
	import { i18n } from '$lib/i18n/index.svelte';
	import type { Preferences } from '$lib/types';

	const { t } = i18n;

	// One neutral placeholder shown while an extraction is in flight and the
	// library is still empty. Deliberately generic -- NOT the video card's
	// aspect-video + quality rows, NOT the gallery's square grid -- so a single
	// skeleton fits whether the result turns out to be a video or an image
	// gallery (we don't know which until it lands). Only rendered when there's
	// nothing on screen yet; once any real result exists the caller hides it.
	let { preferences }: { preferences: Preferences } = $props();
</script>

<section class="mb-10" role="status" aria-busy="true" aria-label={t('extract.loading')}>
	<span class="sr-only">{t('extract.loading')}</span>

	<div
		class="grid gap-4 sm:gap-5 {preferences.layoutList === 'grid'
			? 'grid-cols-1 lg:grid-cols-2'
			: 'grid-cols-1'}"
	>
		<div
			class="border-border/60 bg-card/60 shadow-soft overflow-hidden rounded-2xl border py-3.5 sm:p-4"
		>
			<!-- Header: source icon + label + a small action cluster -->
			<div
				class="border-border/40 mb-3 flex flex-wrap items-center gap-2 border-b px-3.5 pb-2.5 sm:px-0"
			>
				<div class="bg-muted h-3.5 w-3.5 shrink-0 animate-pulse rounded-full"></div>
				<div class="bg-muted h-3.5 w-40 max-w-full animate-pulse rounded"></div>
				<div class="ms-auto flex shrink-0 items-center gap-1.5">
					{#each [0, 1, 2] as j (j)}
						<div class="bg-muted h-7 w-7 animate-pulse rounded-full"></div>
					{/each}
				</div>
			</div>

			<!-- Neutral content block: a plain rounded rectangle, not tied to a
			     specific media shape. -->
			<div class="overflow-hidden rounded-none sm:rounded-xl">
				<div class="bg-muted aspect-[16/10] w-full animate-pulse"></div>
			</div>

			<!-- A couple of text lines + a pill, common to both result kinds. -->
			<div class="space-y-3 px-3.5 pt-3 sm:px-0">
				<div class="bg-muted h-4 w-3/4 animate-pulse rounded"></div>
				<div class="flex items-center justify-between gap-2">
					<div class="bg-muted/70 h-3 w-16 animate-pulse rounded"></div>
					<div class="bg-muted/70 h-6 w-28 animate-pulse rounded-full"></div>
				</div>
			</div>
		</div>
	</div>
</section>
