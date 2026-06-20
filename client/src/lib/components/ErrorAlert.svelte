<script lang="ts">
	import AlertCircle from '@lucide/svelte/icons/alert-circle';

	import * as Alert from '$lib/components/ui/alert';
	import { Button } from '$lib/components/ui/button';
	import { i18n } from '$lib/i18n/index.svelte';
	import { appStore } from '$lib/stores/app-state.svelte';

	const {t} = i18n;

	let {
		videoExtractError
	}: {
		videoExtractError: string | null;
	} = $props();

	let title = $derived(t('error.extractTitle'));
	let message = $derived(videoExtractError);
</script>

<Alert.Root
	variant="destructive"
	class="ds-glass shadow-soft mb-6 rounded-[1.75rem] border-0 ring-1 ring-destructive/25"
>
	<AlertCircle class="h-4 w-4" />
	<Alert.Description
		class="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-start sm:justify-between"
	>
		<div class="min-w-0">
			<p class="mb-1 font-medium">{title}</p>
			<p class="text-xs wrap-break-word">{message}</p>
			<p class="mt-1 text-xs opacity-80">
				{t('error.advice')}
			</p>
		</div>
		<Button
			variant="outline"
			size="sm"
			onclick={() => appStore.clearErrors()}
			class="shrink-0 cursor-pointer self-start"
		>
			{t('error.dismiss')}
		</Button>
	</Alert.Description>
</Alert.Root>
