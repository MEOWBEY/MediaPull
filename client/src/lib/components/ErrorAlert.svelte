<script lang="ts">
	import AlertCircle from '@lucide/svelte/icons/alert-circle';
	import Images from '@lucide/svelte/icons/images';
	import KeyRound from '@lucide/svelte/icons/key-round';
	import RefreshCw from '@lucide/svelte/icons/refresh-cw';
	import Video from '@lucide/svelte/icons/video';
	import X from '@lucide/svelte/icons/x';

	import * as Alert from '$lib/components/ui/alert';
	import { Button } from '$lib/components/ui/button';
	import { extraction } from '$lib/extraction.svelte';
	import { i18n } from '$lib/i18n/index.svelte';
	import { appStore } from '$lib/stores/app-state.svelte';

	const { t } = i18n;

	let {
		videoExtractError,
		onOpenCookies
	}: {
		videoExtractError: string | null;
		/** Opens the preferences sheet (on Cookies once tabs land) so an
		 *  auth-required failure is one tap from fixing. */
		onOpenCookies?: () => void;
	} = $props();

	let title = $derived(t('error.extractTitle'));
	let message = $derived(videoExtractError);

	// A recoverable failure (URL + attempted mode) enables the action buttons.
	let failure = $derived(appStore.lastFailure);

	// Cheap heuristic (server has no machine-readable code yet): auth/login
	// wording means "add cookies" is the likely fix.
	let looksLikeAuth = $derived(
		/login|log in|sign in|sign-in|cookie|auth|401|403|private|members?-only/i.test(message ?? '')
	);

	// Which "try the other type" action to offer. From an auto failure (tried
	// both) we default to offering images, since a wrong video guess is the
	// common case; otherwise offer the opposite of what was tried.
	let otherType = $derived<'video' | 'gallery' | null>(
		!failure ? null : failure.mode === 'gallery' ? 'video' : 'gallery'
	);
</script>

<Alert.Root
	variant="destructive"
	class="relative mb-6 rounded-lg border border-destructive/40 bg-destructive/5"
>
	<!-- Dismiss as a corner X (pinned to the end/top) rather than a text button in
	     the action row -- keeps the recovery actions (Retry / cookies / other type)
	     visually separate from "close this". inset-e-2 mirrors for RTL. -->
	<button
		type="button"
		onclick={() => appStore.clearErrors()}
		aria-label={t('error.dismiss')}
		title={t('error.dismiss')}
		class="border-destructive/30 text-destructive/70 hover:bg-destructive/10 hover:text-destructive hover:border-destructive/50 absolute top-2 inset-e-2 flex h-8 w-8 cursor-pointer items-center justify-center rounded-md border transition-colors"
	>
		<X class="h-4 w-4" />
	</button>

	<AlertCircle class="h-4 w-4" />
	<Alert.Description class="flex min-w-0 flex-col gap-3 pe-8">
		<div class="min-w-0">
			<p class="mb-1 font-medium">{title}</p>
			<p class="text-xs wrap-break-word">{message}</p>
			<p class="mt-1 text-xs opacity-80">
				{looksLikeAuth ? t('error.loginHint') : t('error.advice')}
			</p>
		</div>

		{#if failure}
			<div class="flex flex-wrap items-center gap-2">
				<Button
					variant="default"
					size="sm"
					onclick={() => extraction.retryLastFailure()}
					class="h-9 gap-1.5 sm:h-8"
				>
					<RefreshCw class="h-3.5 w-3.5" />
					{t('error.retry')}
				</Button>

				{#if looksLikeAuth && onOpenCookies}
					<Button variant="outline" size="sm" onclick={onOpenCookies} class="h-9 gap-1.5 sm:h-8">
						<KeyRound class="h-3.5 w-3.5" />
						{t('error.openCookies')}
					</Button>
				{/if}

				{#if otherType === 'gallery'}
					<Button
						variant="outline"
						size="sm"
						onclick={() => extraction.retryLastAsType('gallery')}
						class="h-9 gap-1.5 sm:h-8"
					>
						<Images class="h-3.5 w-3.5" />
						{t('error.tryGallery')}
					</Button>
				{:else if otherType === 'video'}
					<Button
						variant="outline"
						size="sm"
						onclick={() => extraction.retryLastAsType('video')}
						class="h-9 gap-1.5 sm:h-8"
					>
						<Video class="h-3.5 w-3.5" />
						{t('error.tryVideo')}
					</Button>
				{/if}
			</div>
		{/if}
	</Alert.Description>
</Alert.Root>
