<script lang="ts">
	import AlertCircle from '@lucide/svelte/icons/alert-circle';
	import Images from '@lucide/svelte/icons/images';
	import KeyRound from '@lucide/svelte/icons/key-round';
	import RefreshCw from '@lucide/svelte/icons/refresh-cw';
	import Video from '@lucide/svelte/icons/video';

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
	class="ds-glass shadow-soft mb-6 rounded-[1.75rem] border-0 ring-1 ring-destructive/25"
>
	<AlertCircle class="h-4 w-4" />
	<Alert.Description class="flex min-w-0 flex-col gap-3">
		<div class="min-w-0">
			<p class="mb-1 font-medium">{title}</p>
			<p class="text-xs wrap-break-word">{message}</p>
			<p class="mt-1 text-xs opacity-80">
				{looksLikeAuth ? t('error.loginHint') : t('error.advice')}
			</p>
		</div>

		<div class="flex flex-wrap items-center gap-2">
			{#if failure}
				<Button
					variant="default"
					size="sm"
					onclick={() => extraction.retryLastFailure()}
					class="gap-1.5"
				>
					<RefreshCw class="h-3.5 w-3.5" />
					{t('error.retry')}
				</Button>

				{#if looksLikeAuth && onOpenCookies}
					<Button variant="outline" size="sm" onclick={onOpenCookies} class="gap-1.5">
						<KeyRound class="h-3.5 w-3.5" />
						{t('error.openCookies')}
					</Button>
				{/if}

				{#if otherType === 'gallery'}
					<Button
						variant="outline"
						size="sm"
						onclick={() => extraction.retryLastAsType('gallery')}
						class="gap-1.5"
					>
						<Images class="h-3.5 w-3.5" />
						{t('error.tryGallery')}
					</Button>
				{:else if otherType === 'video'}
					<Button
						variant="outline"
						size="sm"
						onclick={() => extraction.retryLastAsType('video')}
						class="gap-1.5"
					>
						<Video class="h-3.5 w-3.5" />
						{t('error.tryVideo')}
					</Button>
				{/if}
			{/if}

			<Button
				variant="ghost"
				size="sm"
				onclick={() => appStore.clearErrors()}
				class="ms-auto shrink-0 cursor-pointer"
			>
				{t('error.dismiss')}
			</Button>
		</div>
	</Alert.Description>
</Alert.Root>
