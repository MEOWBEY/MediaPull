<script lang="ts">
	import ClipboardPaste from '@lucide/svelte/icons/clipboard-paste';
	import ImageIcon from '@lucide/svelte/icons/image';
	import Loader2 from '@lucide/svelte/icons/loader-2';
	import Search from '@lucide/svelte/icons/search';
	import Sparkles from '@lucide/svelte/icons/sparkles';
	import VideoIcon from '@lucide/svelte/icons/video';
	import X from '@lucide/svelte/icons/x';
	import { toast } from 'svelte-sonner';

	import { Button } from '$lib/components/ui/button';
	import { i18n } from '$lib/i18n/index.svelte';
	import { appStore } from '$lib/stores/app-state.svelte';

	const { t } = i18n;

	let {
		runVideoExtractFromServer,
		cancelActiveOperation,
		isVideoExtractRunning,
		batchTotal = 0,
		batchDone = 0
	} = $props();

	let inputUrl = $state('');
	// batchTotal stays > 0 for the whole queue, so the running state doesn't flicker
	// between individual items (keeps the input disabled + cancel button visible).
	let isBatchRunning = $derived(batchTotal > 0);
	let isOperationRunning = $derived(isVideoExtractRunning || isBatchRunning);

	// 'auto' (the default) tries video first and silently falls back to
	// gallery -- see ExtractionController.extractAuto. This row is always
	// visible so first-run users can see (and change) whether we'll pull a
	// video, a gallery, or auto-detect -- without hunting through Preferences.
	let contentTypeMode = $derived(appStore.preferences.contentTypeMode);

	function setContentTypeMode(mode: 'auto' | 'video' | 'gallery') {
		appStore.updatePreferences({ contentTypeMode: mode });
	}

	const contentTypeOptions = [
		{ mode: 'auto', icon: Sparkles, labelKey: 'prefs.contentType.auto' },
		{ mode: 'video', icon: VideoIcon, labelKey: 'prefs.contentType.video' },
		{ mode: 'gallery', icon: ImageIcon, labelKey: 'prefs.contentType.gallery' }
	] as const;

	// How many URLs the field currently holds (pasted multi-line collapses to
	// spaces in a single-line input, so whitespace-splitting catches a batch).
	let urlCount = $derived(inputUrl.trim().split(/\s+/).filter(Boolean).length);

	function clearInputUrl() {
		if (isOperationRunning) {
			return;
		}
		inputUrl = '';
	}

	// Paste from the clipboard into the field. The async Clipboard API
	// (navigator.clipboard.readText) is unavailable or blocked on many mobile
	// browsers, so we try it first, and on any failure fall back to focusing the
	// field and surfacing a hint — the user's own paste gesture / keyboard then
	// works normally.
	async function pasteFromClipboard() {
		if (isOperationRunning) {
			return;
		}

		const field = document.getElementById('video-url') as HTMLInputElement | null;
		const canUseAsyncApi = window.isSecureContext && navigator.clipboard?.readText;

		if (!canUseAsyncApi) {
			field?.focus();
			field?.select();
			toast.info(t('input.pasteHint'));

			return;
		}

		try {
			const text = await navigator.clipboard.readText();

			if (text) {
				inputUrl = text.trim();
				field?.focus();
			} else {
				field?.focus();
				field?.select();
				toast.info(t('input.pasteHint'));
			}
		} catch {
			field?.focus();
			field?.select();
			toast.info(t('input.pasteHint'));
		}
	}

	// Native form submit -- lets the browser record submitted URLs in its own
	// autofill history (name="url" + a real submit), so past links reappear as
	// suggestions next time. preventDefault stops an actual page navigation, and
	// Enter in the single-line field triggers this submit natively.
	function onSubmit(event: SubmitEvent) {
		event.preventDefault();
		if (inputUrl.trim() && !isOperationRunning) {
			runVideoExtractFromServer(inputUrl);
		}
	}
</script>

<div class="mx-auto w-full text-start">
	<!-- focus-within border: the URL input itself is borderless inside this
	     container, so the container must carry the visible keyboard-focus cue. -->
	<form
		class="ds-glass shadow-float focus-within:border-signal/60 overflow-hidden rounded-lg transition-colors"
		onsubmit={onSubmit}
	>
		<!-- Input row: a mono `URL>` prompt makes the field read as a command line.
		     dir=ltr pins the `>` after "URL" — as bidi-neutral punctuation it would
		     otherwise mirror to the wrong side under RTL. -->
		<div class="flex items-center gap-2 ps-3.5 pe-2 py-2">
			<span
				dir="ltr"
				class="text-signal font-mono text-sm font-bold select-none"
				aria-hidden="true"
			>
				URL&gt;
			</span>
			<div class="relative flex-1">
				<input
					id="video-url"
					name="url"
					bind:value={inputUrl}
					aria-label={contentTypeMode === 'gallery'
						? t('input.placeholderGallery')
						: t('input.placeholder')}
					placeholder={contentTypeMode === 'gallery'
						? t('input.placeholderGallery')
						: t('input.placeholder')}
					disabled={isOperationRunning}
					autocomplete="on"
					autocapitalize="off"
					spellcheck="false"
					class="placeholder:text-muted-foreground/60 h-10 w-full border-0 bg-transparent pe-10 font-mono text-sm outline-none disabled:opacity-60 sm:text-base"
				/>
				{#if inputUrl}
					<button
						type="button"
						onclick={clearInputUrl}
						disabled={isOperationRunning}
						aria-label={t('input.clear')}
						class="text-muted-foreground hover:bg-muted hover:text-foreground absolute top-1/2 inset-e-0 flex h-8 w-8 -translate-y-1/2 cursor-pointer items-center justify-center rounded-md transition-colors"
					>
						<X class="h-4 w-4" />
					</button>
				{/if}
			</div>

			<!-- Paste is the first thing most visits do, so it's a labeled action
			     right in the field rather than relying on the OS paste gesture. -->
			<Button
				variant="outline"
				size="sm"
				onclick={pasteFromClipboard}
				disabled={isOperationRunning}
				class="h-9 shrink-0"
				title={t('input.paste')}
			>
				<ClipboardPaste class="h-4 w-4 sm:me-1.5" />
				<span class="hidden sm:inline">{t('input.paste')}</span>
			</Button>
		</div>

		{#if urlCount > 1 && !isOperationRunning}
			<p class="text-muted-foreground border-border/60 border-t px-3.5 py-2 font-mono text-xs">
				{t('input.batchHint', { n: urlCount })}
			</p>
		{/if}

		<!-- Action row -->
		<div class="border-border/60 flex flex-wrap items-center gap-2 border-t p-2">
			<!-- Mode selector only appears once the user has forced video/gallery.
			     In 'auto' (the default) it's hidden — most pastes want auto and the
			     buttons would just add clutter. Mode stays changeable in Preferences. -->
			{#if contentTypeMode !== 'auto'}
				<div
					class="border-border/70 flex shrink-0 items-center overflow-hidden rounded-md border font-mono text-xs"
					role="group"
					aria-label={t('input.mode')}
				>
					{#each contentTypeOptions as option, i (option.mode)}
						<button
							type="button"
							disabled={isOperationRunning}
							onclick={() => setContentTypeMode(option.mode)}
							aria-pressed={contentTypeMode === option.mode}
							title={t(option.labelKey)}
							class={[
								'flex items-center gap-1.5 px-2.5 py-2 transition-colors disabled:opacity-50 sm:py-1.5',
								i > 0 && 'border-border/70 border-s',
								contentTypeMode === option.mode
									? 'bg-signal/15 text-signal font-semibold'
									: 'text-muted-foreground hover:bg-muted hover:text-foreground'
							]}
						>
							<option.icon class="h-3.5 w-3.5" />
							<span class="hidden sm:inline">{t(option.labelKey)}</span>
						</button>
					{/each}
				</div>
			{/if}

			<Button
				type="submit"
				disabled={!inputUrl.trim() || isOperationRunning}
				class="h-9 flex-1 font-bold sm:flex-none sm:px-6"
			>
				{#if isVideoExtractRunning || isBatchRunning}
					<Loader2 class="me-2 h-4 w-4 animate-spin" />
					{t('input.extracting')}
					{#if batchTotal > 1}<span class="ms-1 tabular-nums">{batchDone}/{batchTotal}</span>{/if}
				{:else}
					<Search class="me-2 h-4 w-4" />
					{t('input.extract')}
					{#if urlCount > 1}<span class="ms-1 tabular-nums">({urlCount})</span>{/if}
				{/if}
			</Button>

			{#if isOperationRunning}
				<div class="ms-auto flex items-center gap-2">
					<Button
						variant="destructive"
						onclick={cancelActiveOperation}
						class="h-9 px-4"
						title={t('input.cancel')}
						aria-label={t('input.cancel')}
					>
						<X class="h-4 w-4 sm:me-1.5" />
						<span class="hidden sm:inline">{t('input.cancel')}</span>
					</Button>
				</div>
			{/if}
		</div>
	</form>
</div>
