<script lang="ts">
	import Clock from '@lucide/svelte/icons/clock';
	import Globe from '@lucide/svelte/icons/globe';
	import ImageIcon from '@lucide/svelte/icons/image';
	import Loader2 from '@lucide/svelte/icons/loader-2';
	import Search from '@lucide/svelte/icons/search';
	import Settings from '@lucide/svelte/icons/settings';
	import VideoIcon from '@lucide/svelte/icons/video';
	import X from '@lucide/svelte/icons/x';

	import { Button } from '$lib/components/ui/button';
	import { i18n } from '$lib/i18n/index.svelte';
	import { appStore } from '$lib/stores/app-state.svelte';

	const {t} = i18n;

	let {
		runVideoExtractFromServer,
		cancelActiveOperation,
		isVideoExtractRunning,
		elapsedOperationSeconds = 0,
		batchTotal = 0,
		batchDone = 0,
		isPreferencesDialogOpen = $bindable()
	} = $props();

	let inputUrl = $state('');
	// batchTotal stays > 0 for the whole queue, so the running state doesn't flicker
	// between individual items (keeps the input disabled + cancel button visible).
	let isBatchRunning = $derived(batchTotal > 0);
	let isOperationRunning = $derived(isVideoExtractRunning || isBatchRunning);

	// Which endpoint the input routes to -- surfaced here (not just buried in
	// Preferences) since it's the single most consequential choice before
	// hitting Extract. No server-side auto-detection, so this toggle IS the
	// routing decision.
	let contentTypeMode = $derived(appStore.preferences.contentTypeMode);

	function setContentTypeMode(mode: 'video' | 'gallery') {
		appStore.updatePreferences({ contentTypeMode: mode });
	}

	// How many URLs the field currently holds (pasted multi-line collapses to
	// spaces in a single-line input, so whitespace-splitting catches a batch).
	let urlCount = $derived(inputUrl.trim().split(/\s+/).filter(Boolean).length);

	function clearInputUrl() {
		if (isOperationRunning) {return;}
		inputUrl = '';
	}

	function elapsed(seconds: number): string {
		const mins = Math.floor(seconds / 60);
		const secs = (seconds % 60).toString().padStart(2, '0');

		return `${mins}:${secs}`;
	}

	function onKeydown(event: KeyboardEvent) {
		if (event.key === 'Enter' && inputUrl.trim() && !isOperationRunning) {
			runVideoExtractFromServer(inputUrl);
		}
	}
</script>

<div class="mx-auto w-full text-start">
	<div class="bg-card/80 border-border/60 shadow-soft rounded-4xl border p-2 sm:p-2.5">
		<!-- Input row -->
		<div class="flex items-center gap-2">
			<div class="relative flex-1">
				<Globe class="text-muted-foreground absolute top-1/2 inset-s-3.5 h-5 w-5 -translate-y-1/2" />
				<input
					id="video-url"
					bind:value={inputUrl}
					onkeydown={onKeydown}
					placeholder={contentTypeMode === 'gallery'
						? t('input.placeholderGallery')
						: t('input.placeholder')}
					disabled={isOperationRunning}
					autocomplete="off"
					autocapitalize="off"
					spellcheck="false"
					class="h-12 w-full rounded-full border-0 bg-transparent pe-10 ps-11 text-base outline-none placeholder:text-muted-foreground/70 disabled:opacity-60"
				/>
				{#if inputUrl}
					<button
						type="button"
						onclick={clearInputUrl}
						disabled={isOperationRunning}
						aria-label={t('input.clear')}
						class="text-muted-foreground hover:bg-muted hover:text-foreground absolute top-1/2 inset-e-2 flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-full transition-colors"
					>
						<X class="h-4 w-4" />
					</button>
				{/if}
			</div>

			<button
				type="button"
				onclick={() => (isPreferencesDialogOpen = true)}
				title={t('input.preferences')}
				aria-label={t('input.preferences')}
				class="text-muted-foreground hover:bg-muted hover:text-foreground flex h-10 w-10 shrink-0 items-center justify-center rounded-full transition-colors"
			>
				<Settings class="h-5 w-5" />
			</button>
		</div>

		{#if urlCount > 1 && !isOperationRunning}
			<p class="text-muted-foreground mt-2 px-3 text-xs">{t('input.batchHint', { n: urlCount })}</p>
		{/if}

		<!-- Action row -->
		<div class="mt-2 flex flex-wrap items-center gap-2 border-t border-border/60 pt-2">
			<div class="bg-muted/50 flex shrink-0 items-center gap-0.5 rounded-full p-0.5">
				<Button
					variant={contentTypeMode === 'video' ? 'default' : 'ghost'}
					size="sm"
					disabled={isOperationRunning}
					onclick={() => setContentTypeMode('video')}
					class="gap-1 rounded-full px-2.5 py-1 text-xs"
					title={t('prefs.contentType.video')}
				>
					<VideoIcon class="h-3 w-3" />
					<span>{t('prefs.contentType.video')}</span>
				</Button>
				<Button
					variant={contentTypeMode === 'gallery' ? 'default' : 'ghost'}
					size="sm"
					disabled={isOperationRunning}
					onclick={() => setContentTypeMode('gallery')}
					class="gap-1 rounded-full px-2.5 py-1 text-xs"
					title={t('prefs.contentType.gallery')}
				>
					<ImageIcon class="h-3 w-3" />
					<span>{t('prefs.contentType.gallery')}</span>
				</Button>
			</div>

			<Button
				onclick={() => runVideoExtractFromServer(inputUrl)}
				disabled={!inputUrl.trim() || isOperationRunning}
				class="bg-primary text-primary-foreground hover:bg-primary/90 h-11 flex-1 cursor-pointer rounded-full font-semibold transition-colors sm:flex-none sm:px-6"
			>
				{#if isVideoExtractRunning || isBatchRunning}
					<Loader2 class="me-2 h-4 w-4 animate-spin" /> {t('input.extracting')}
					{#if batchTotal > 1}<span class="ms-1 tabular-nums">{batchDone}/{batchTotal}</span>{/if}
				{:else}
					<Search class="me-2 h-4 w-4" /> {t('input.extract')}
					{#if urlCount > 1}<span class="ms-1 tabular-nums">({urlCount})</span>{/if}
				{/if}
			</Button>

			{#if isOperationRunning}
				<div class="ms-auto flex items-center gap-2">
					<span
						class="bg-primary/10 text-primary hidden items-center gap-1.5 rounded-full px-3 py-2 font-mono text-sm font-medium tabular-nums sm:inline-flex"
						aria-live="polite"
					>
						<Clock class="h-3.5 w-3.5" />
						{elapsed(elapsedOperationSeconds)}
					</span>
					<Button
						variant="destructive"
						onclick={cancelActiveOperation}
						class="h-11 cursor-pointer rounded-full px-4"
						title={t('input.cancel')}
						aria-label={t('input.cancel')}
					>
						<X class="h-4 w-4 sm:me-1.5" />
						<span class="hidden sm:inline">{t('input.cancel')}</span>
					</Button>
				</div>
			{/if}
		</div>
	</div>
</div>
