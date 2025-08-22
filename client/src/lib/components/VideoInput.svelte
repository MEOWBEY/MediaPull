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

	import { videoStore } from '$lib/stores/app-state.svelte';

	interface Props {
		handleExtractVideos: () => Promise<void>;
		handlePuppeteerProxyUrlVideo: (video?: any) => Promise<void>;
		handleCancelOperation: () => void;
		isOperationRunning: boolean;
	}

	let {
		handleExtractVideos,
		handlePuppeteerProxyUrlVideo,
		handleCancelOperation,
		isOperationRunning
	}: Props = $props();

	let inputUrl = $state('');

	let preferences = $derived(videoStore.preferences);
	let isExtracting = $derived(videoStore.extracting);
	let isPuppeteerProxyingUrl = $derived(videoStore.puppeteerProxyingUrl);

	$effect(() => {
		videoStore.updateInputUrl(inputUrl);
	});

	function clearInput() {
		if (isOperationRunning) return;
		inputUrl = '';
		videoStore.reset();
		toast.info('Input cleared');
	}

	function handleKeyPress(event: KeyboardEvent) {
		if (!preferences.keyboardShortcuts) return;
		if (event.key === 'Enter' && !isOperationRunning) handleExtractVideos();
		if (event.key === 'Escape' && isOperationRunning) handleCancelOperation();
	}
</script>

<Card class="mb-6">
	<CardHeader class={preferences.compactMode ? 'pb-2' : 'pb-4'}>
		<CardTitle class="flex items-center gap-2 {preferences.compactMode ? 'text-base' : 'text-lg'}">
			<Unlink class="h-5 w-5 text-blue-600" />
			Video Downloader
		</CardTitle>
		<CardDescription
			>Enter a video URL to extract formats or puppeteerProxyUrl directly</CardDescription
		>
	</CardHeader>
	<CardContent class={preferences.compactMode ? 'space-y-2' : 'space-y-4'}>
		<div class="flex gap-2">
			<div class="relative flex-1">
				<Link2 class="absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-gray-500" />
				<Input
					id="video-url"
					bind:value={inputUrl}
					placeholder="https://example.com/video"
					disabled={isOperationRunning}
					class="cursor-text pl-10"
					onkeydown={handleKeyPress}
				/>
			</div>
			{#if inputUrl}
				<Button
					variant="outline"
					size="icon"
					onclick={clearInput}
					disabled={isOperationRunning}
					class="cursor-pointer"
				>
					<X class="h-4 w-4" />
				</Button>
			{/if}
		</div>
		<div class="flex flex-col flex-wrap gap-2 md:flex-row">
			<Button
				onclick={handleExtractVideos}
				disabled={!inputUrl.trim() || isOperationRunning}
				class="cursor-pointer transition-all duration-200"
			>
				{#if isExtracting}
					<Loader2 class="mr-2 h-4 w-4 animate-spin" />
					Extracting...
				{:else}
					<Search class="mr-2 h-4 w-4" />
					Extract Formats
				{/if}
			</Button>
			<div class="flex items-center gap-2">
				<Button
					variant="secondary"
					onclick={() => handlePuppeteerProxyUrlVideo()}
					disabled={!inputUrl.trim() || isOperationRunning}
					class="cursor-pointer border bg-gray-200 hover:bg-gray-300 dark:bg-zinc-800 hover:dark:bg-zinc-700 {isOperationRunning
						? 'w-[calc(100%-50px)]'
						: 'w-full md:w-auto'}"
				>
					{#if isPuppeteerProxyingUrl}
						<Loader2 class="mr-2 h-4 w-4 animate-spin" />
						PuppeteerProxyingUrl...
					{:else}
						<Waypoints class="mr-2 h-4 w-4" />
						PuppeteerProxyUrl
					{/if}
				</Button>

				{#if isOperationRunning}
					<Button
						variant="destructive"
						onclick={handleCancelOperation}
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
