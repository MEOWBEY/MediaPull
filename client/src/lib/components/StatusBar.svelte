<script lang="ts">
	import { Button } from '$lib/components/ui/button';
	import Clock from 'lucide-svelte/icons/clock';
	import Settings from 'lucide-svelte/icons/settings';
	import { videoStore } from '$lib/stores/app-state.svelte';

	interface Props {
		operationTimer: number;
		isOperationRunning: boolean;
		showPreferences: boolean;
	}

	let { operationTimer, isOperationRunning, showPreferences = $bindable() }: Props = $props();

	let processedVideos = $derived(videoStore.getSortedProcessedVideos());
	let processingQueue = $derived(videoStore.processingQueue);
	let processingError = $derived(videoStore.processingError);
	let extractionError = $derived(videoStore.extractionError);
	let hasErrors = $derived(Boolean(processingError || extractionError));
	let hasProcessedVideos = $derived(processedVideos.length > 0);
	let isExtracting = $derived(videoStore.extracting);
	let isProcessing = $derived(videoStore.processing);

	let operationStatus = $derived(() => {
		if (isExtracting) return { color: 'bg-blue-500', text: 'Extracting...' };
		if (isProcessing) return { color: 'bg-blue-500', text: 'Processing...' };
		if (processingQueue.size > 0)
			return { color: 'bg-yellow-500', text: `${processingQueue.size} in queue` };
		if (hasProcessedVideos) return { color: 'bg-green-500', text: 'Ready' };
		if (hasErrors) return { color: 'bg-red-500', text: 'Error' };
		return { color: 'bg-gray-400', text: 'Idle' };
	});

	function formatTimer(seconds: number): string {
		const mins = Math.floor(seconds / 60);
		const secs = seconds % 60;
		return `${mins}:${secs.toString().padStart(2, '0')}`;
	}
</script>

<div class="mb-6 flex items-center justify-between">
	<div class="flex items-center gap-3">
		<div class="flex items-center gap-2 rounded-lg bg-white px-3 py-2 dark:bg-card">
			<div class="h-2 w-2 rounded-full {operationStatus().color}"></div>
			<span class="text-sm font-medium">{operationStatus().text}</span>
		</div>
		{#if isOperationRunning}
			<div class="flex items-center gap-1 rounded-lg bg-blue-50 px-3 py-2 dark:bg-blue-900/30">
				<Clock class="h-3 w-3 text-blue-600 dark:text-blue-400" />
				<span class="font-mono text-sm text-blue-600 dark:text-blue-400">
					{formatTimer(operationTimer)}
				</span>
			</div>
		{/if}
	</div>
	<div class="flex items-center gap-2">
		<Button
			variant="ghost"
			size="sm"
			class="rounded-lg bg-white hover:bg-gray-200 px-3 py-2 dark:bg-card dark:hover:bg-zinc-700"
			onclick={() => (showPreferences = true)}
		>
			<Settings class="h-4 w-4" />
		</Button>
	</div>
</div>
