<script lang="ts">
	import { Button } from '$lib/components/ui/button';
	import * as Alert from '$lib/components/ui/alert';
	import AlertCircle from 'lucide-svelte/icons/alert-circle';
	import { appStore } from '$lib/stores/app-state.svelte';
	let {
		ovcProxyError,
		videoExtractError,
	} = $props();

</script>

<Alert.Root variant="destructive" class="mb-6 border-none dark:bg-zinc-900">
	<AlertCircle class="h-4 w-4" />
	<Alert.Description class="flex items-start justify-between">
		<div>
			<p class="mb-1 font-medium">Error</p>
			<p class="max-w-2xl text-xs">{videoExtractError || ovcProxyError}</p>
		</div>
		<Button
			variant="outline"
			size="sm"
			onclick={() => appStore.clearErrors()}
			class="cursor-pointer"
		>
			Dismiss
		</Button>
	</Alert.Description>
</Alert.Root>
