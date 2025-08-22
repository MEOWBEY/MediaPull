<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { Button } from '$lib/components/ui/button';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';

	import Download from 'lucide-svelte/icons/download';
	import Copy from 'lucide-svelte/icons/copy';
	import Trash2 from 'lucide-svelte/icons/trash-2';
	import Waypoints from 'lucide-svelte/icons/waypoints';

	import VideoPlayer from '$lib/components/VideoPlayer.svelte';
	import { videoStore, type PuppeteerProxiedUrlVideo } from '$lib/stores/app-state.svelte';

	let puppeteerProxiedUrlVideoPreviewStates = $state(new Map<string, boolean>());

	let puppeteerProxiedUrlVideos = $derived(videoStore.getSortedPuppeteerProxiedUrlVideos());
	let preferences = $derived(videoStore.preferences);
	let hasPuppeteerProxiedUrlVideos = $derived(puppeteerProxiedUrlVideos.length > 0);

	// Helper functions
	async function copyToClipboard(text: string, id: string) {
		try {
			await navigator.clipboard.writeText(text);
			toast.success('Copied to clipboard');
			const element = document.querySelector(`[data-copy-id="${id}"]`);
			if (element) {
				element.classList.add('text-green-500');
				setTimeout(() => element.classList.remove('text-green-500'), 2000);
			}
		} catch (error) {
			toast.error('Failed to copy');
		}
	}

	function clearPuppeteerProxiedUrlVideos() {
		videoStore.clearPuppeteerProxiedUrlVideos();
		puppeteerProxiedUrlVideoPreviewStates.clear();
		toast.info('PuppeteerProxiedUrl videos cleared');
	}

	function downloadVideo(video: PuppeteerProxiedUrlVideo) {
		// Always use download URL for puppeteerProxiedUrl videos
		window.open(video.downloadUrl, '_blank');
	}

	function copyVideoUrl(video: PuppeteerProxiedUrlVideo, id: string) {
		// Always use download URL for puppeteerProxiedUrl videos
		copyToClipboard(video.downloadUrl, id);
	}
</script>

{#if hasPuppeteerProxiedUrlVideos}
	<Card class="mb-6 ">
		<CardHeader
			class={preferences.compactMode
				? 'border-b py-3 [.border-b]:pb-2'
				: ' border-b [.border-b]:pb-3'}
		>
			<div class="flex items-center justify-between">
				<CardTitle
					class="flex items-center gap-2 {preferences.compactMode
						? 'text-xs md:text-sm'
						: 'text-base md:text-lg'}"
				>
					<Waypoints class="h-4 w-4 shrink-0 text-green-600" />
					PuppeteerProxiedUrl
				</CardTitle>
				<Button
					variant="outline"
					size="sm"
					onclick={clearPuppeteerProxiedUrlVideos}
					class="cursor-pointer"
				>
					<Trash2 class="mr-2 h-4 w-4" />
					Clear
				</Button>
			</div>
		</CardHeader>

		<CardContent>
			<div
				class="grid {preferences.compactMode ? 'gap-2' : 'gap-4'} {preferences.viewMode === 'grid'
					? 'sm:grid-cols-2'
					: 'grid-cols-1'}"
			>
				{#each puppeteerProxiedUrlVideos as video (video.id)}
					<div class="group relative rounded-lg">
						<div
							class="flex items-start justify-between gap-4 {preferences.compactMode
								? 'mb-2'
								: 'mb-3'}"
						>
							<div class="flex items-center gap-3">
								<div>
									<h4
										class="font-semibold text-gray-900 dark:text-gray-100 {preferences.compactMode
											? 'text-sm'
											: 'text-base'}"
									>
										Proxied
									</h4>
								</div>
							</div>

							<div class="flex gap-1.5">
								<Button
									variant="outline"
									size="icon"
									onclick={() => copyVideoUrl(video, `puppeteerProxiedUrl-${video.id}`)}
									data-copy-id="puppeteerProxiedUrl-{video.id}"
									class="cursor-pointer"
									title="Copy URL"
								>
									<Copy class="h-4 w-4" />
								</Button>
								<Button
									onclick={() => downloadVideo(video)}
									class="cursor-pointer bg-green-600 hover:bg-green-700"
									size="icon"
									title="Download"
								>
									<Download class="h-4 w-4" />
								</Button>
							</div>
						</div>

						<div class="mt-2">
							<VideoPlayer
								poster={preferences.showThumbnails ? video.thumbnail : ''}
								muted={preferences.muteByDefault}
								preload={preferences.preloadMetadata ? 'metadata' : 'none'}
								qualities={[
									{
										src: video.downloadUrl,
										label: video.quality || 'Default'
									}
								]}
							/>
						</div>
					</div>
				{/each}
			</div>
		</CardContent>
	</Card>
{/if}
