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
			class="border-border/70 bg-card/60 overflow-hidden rounded-lg border py-3.5"
		>
			<!-- Header: source icon + label + a small action cluster -->
			<div
				class="border-border/60 mb-3 flex flex-wrap items-center gap-2 border-b pb-2.5"
			>
				<div class="bg-muted h-3.5 w-3.5 shrink-0 animate-pulse rounded-sm"></div>
				<div class="bg-muted h-3.5 w-40 max-w-full animate-pulse rounded-sm"></div>
				<div class="ms-auto flex shrink-0 items-center gap-1.5">
					{#each [0, 1, 2] as j (j)}
						<div class="bg-muted h-7 w-7 animate-pulse rounded-sm"></div>
					{/each}
				</div>
			</div>

			<!-- In row layout the media block sits on the start side with the text
			     lines beside it (at lg+, matching the real card); otherwise it stacks. -->
			<div class={preferences.layoutList === 'row' ? 'lg:flex lg:items-start lg:gap-5' : ''}>
				<div
					class="overflow-hidden rounded-none sm:rounded-md {preferences.layoutList === 'row'
						? 'lg:w-full lg:max-w-xl'
						: ''}"
				>
					<div class="bg-muted aspect-16/10 w-full animate-pulse"></div>
				</div>

				<!-- A couple of text lines + a pill, common to both result kinds. -->
				<div
					class="space-y-3 pt-3 {preferences.layoutList === 'row'
						? 'lg:flex-1 lg:pt-0'
						: ''}"
				>
					<div class="bg-muted h-4 w-3/4 animate-pulse rounded-sm"></div>
					<div class="flex items-center justify-between gap-2">
						<div class="bg-muted/70 h-3 w-16 animate-pulse rounded-sm"></div>
						<div class="bg-muted/70 h-6 w-28 animate-pulse rounded-sm"></div>
					</div>
				</div>
			</div>
		</div>
	</div>
</section>
