<script lang="ts">
	import { Button } from '$lib/components/ui/button';
	import Clock from 'lucide-svelte/icons/clock';
	import Settings from 'lucide-svelte/icons/settings';

	let {
		elapsedOperationSeconds,
		isVideoExtractRunning,
		isOVCProxyRunning,
		videoExtractError,
		ovcProxyError,
		isPreferencesDialogOpen = $bindable()
	} = $props();

	let operationStatus = $derived(() => {
		if (isVideoExtractRunning) return { color: 'bg-blue-500', text: 'isVideoExtractRunning...' };
		if (isOVCProxyRunning) return { color: 'bg-blue-500', text: 'isOVCProxyRunning...' };
		if (videoExtractError || ovcProxyError) return { color: 'bg-red-500', text: 'Error' };
		return { color: 'bg-gray-400', text: 'Idle' };
	});

	function formatElapsedTime(seconds: number): string {
		const mins = Math.floor(seconds / 60);
		const secs = seconds % 60;
		return `${mins}:${secs.toString().padStart(2, '0')}`;
	}
</script>

<div class="mb-6 flex items-center justify-between">
	<div class="flex items-center gap-3">
		<div class="dark:bg-card flex items-center gap-2 rounded-lg bg-white px-3 py-2">
			<div class="h-2 w-2 rounded-full {operationStatus().color}"></div>
			<span class="text-sm font-medium">{operationStatus().text}</span>
		</div>
		{#if isVideoExtractRunning || isOVCProxyRunning}
			<div class="flex items-center gap-1 rounded-lg bg-blue-50 px-3 py-2 dark:bg-blue-900/30">
				<Clock class="h-3 w-3 text-blue-600 dark:text-blue-400" />
				<span class="font-mono text-sm text-blue-600 dark:text-blue-400">
					{formatElapsedTime(elapsedOperationSeconds)}
				</span>
			</div>
		{/if}
	</div>
	<div class="flex items-center gap-2">
		<Button
			variant="ghost"
			size="sm"
			class="dark:bg-card rounded-lg bg-white px-3 py-2 hover:bg-gray-200 dark:hover:bg-zinc-700"
			onclick={() => (isPreferencesDialogOpen = true)}
		>
			<Settings class="h-4 w-4" />
		</Button>
	</div>
</div>
