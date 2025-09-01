<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import {
		Card,
		CardContent,
		CardDescription,
		CardHeader,
		CardTitle
	} from '$lib/components/ui/card';

	import Unlink from 'lucide-svelte/icons/unlink';
	import Link2 from 'lucide-svelte/icons/link-2';
	import X from 'lucide-svelte/icons/x';
	import SearchX from 'lucide-svelte/icons/search-x';
	import Search from 'lucide-svelte/icons/search';
	import Waypoints from 'lucide-svelte/icons/waypoints';
	import Loader2 from 'lucide-svelte/icons/loader-2';

	let {
		runVideoExtractFromServer,
		runOvcProxyFromServer,
		cancelActiveOperation,
		isVideoExtractRunning,
		isOVCProxyRunning,
		preferences
	} = $props();

	let inputUrl = $state('');
	let isOperationRunning = $derived(isVideoExtractRunning || isOVCProxyRunning);

	function clearInputUrl() {
		if (isOperationRunning) return;
		inputUrl = '';
		toast.info('Input cleared');
	}
</script>

<Card class="mb-6">
	<CardHeader class={preferences.enableCompact ? 'pb-2' : 'pb-4'}>
		<CardTitle
			class="flex items-center gap-2 {preferences.enableCompact ? 'text-base' : 'text-lg'}"
		>
			<Unlink class="h-5 w-5 text-blue-600" />
			Video Downloader
		</CardTitle>
		<CardDescription>Enter a video URL to extract formats or use OVC proxy directly</CardDescription
		>
	</CardHeader>
	<CardContent class={preferences.enableCompact ? 'space-y-2' : 'space-y-4'}>
		<div class="flex gap-2">
			<div class="relative flex-1">
				<Link2 class="absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-gray-500" />
				<Input
					id="video-url"
					bind:value={inputUrl}
					placeholder="https://example.com/video"
					disabled={isOperationRunning}
					class="cursor-text pl-10"
				/>
			</div>
			{#if inputUrl}
				<Button
					variant="outline"
					size="icon"
					onclick={clearInputUrl}
					disabled={isOperationRunning}
					class="cursor-pointer"
				>
					<X class="h-4 w-4" />
				</Button>
			{/if}
		</div>
		<div class="flex flex-col flex-wrap gap-2 md:flex-row">
			<Button
				onclick={() => runVideoExtractFromServer(inputUrl)}
				disabled={!inputUrl.trim() || isOperationRunning}
				class="cursor-pointer transition-all duration-200"
			>
				{#if isVideoExtractRunning}
					<Loader2 class="mr-2 h-4 w-4 animate-spin" />
					isVideoExtractRunning ...
				{:else}
					<Search class="mr-2 h-4 w-4" />
					Extract Formats
				{/if}
			</Button>
			<div class="flex items-center gap-2">
				<Button
					variant="secondary"
					onclick={() => runOvcProxyFromServer(inputUrl)}
					disabled={!inputUrl.trim() || isOperationRunning}
					class="cursor-pointer border bg-gray-200 hover:bg-gray-300 dark:bg-zinc-800 hover:dark:bg-zinc-700 {isOperationRunning
						? 'w-[calc(100%-50px)]'
						: 'w-full md:w-auto'}"
				>
					{#if isOVCProxyRunning}
						<Loader2 class="mr-2 h-4 w-4 animate-spin" />
						isOVCProxyRunning...
					{:else}
						<Waypoints class="mr-2 h-4 w-4" />
						Ovc proxy
					{/if}
				</Button>

				{#if isOperationRunning}
					<Button
						variant="destructive"
						onclick={cancelActiveOperation}
						size="icon"
						class="ml-2 cursor-pointer"
					>
						<SearchX class="h-4 w-4" />
					</Button>
				{/if}
			</div>
		</div>
	</CardContent>
</Card>
