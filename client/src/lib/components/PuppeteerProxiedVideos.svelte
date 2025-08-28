<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { Button } from '$lib/components/ui/button';
	import {
		Card,
		CardContent,
		CardHeader,
		CardTitle,
		CardDescription
	} from '$lib/components/ui/card';

	import Download from 'lucide-svelte/icons/download';
	import Trash2 from 'lucide-svelte/icons/trash-2';
	import Waypoints from 'lucide-svelte/icons/waypoints';

	import VideoPlayer from '$lib/components/VideoPlayer.svelte';
	import { videoStore, type PuppeteerProxiedUrlVideo } from '$lib/stores/app-state.svelte';

	let puppeteerProxiedUrlVideoPreviewStates = $state(new Map<string, boolean>());

	let puppeteerProxiedUrlVideos = $derived(videoStore.getSortedPuppeteerProxiedUrlVideos());
	let preferences = $derived(videoStore.preferences);
	let hasPuppeteerProxiedUrlVideos = $derived(puppeteerProxiedUrlVideos.length > 0);

	function clearPuppeteerProxiedUrlVideos() {
		videoStore.clearPuppeteerProxiedUrlVideos();
		puppeteerProxiedUrlVideoPreviewStates.clear();
		toast.info('PuppeteerProxiedUrl videos cleared');
	}

	function downloadVideo(video: PuppeteerProxiedUrlVideo) {
		// Always use download URL for puppeteerProxiedUrl videos
		window.open(video.downloadUrl, '_blank');
	}
</script>

{#if hasPuppeteerProxiedUrlVideos}
	<Card class="bg-card dark:bg-card-dark mx-auto mb-6">
		<CardHeader>
			<div class="flex items-center justify-between gap-4">
				<div class="flex items-center gap-3">
					<span
						class="flex items-center justify-center rounded-full bg-gray-200 p-3 dark:bg-zinc-800"
					>
						<Waypoints class="h-5 w-5 shrink-0 text-amber-600" />
					</span>
					<div class="min-w-0">
						<CardTitle
							class="line-clamp-1 flex items-center gap-2 {preferences.compactMode
								? 'text-sm'
								: 'text-base'}"
						>
							Puppeteer Proxied Videos ({puppeteerProxiedUrlVideos.length})
						</CardTitle>
						<CardDescription class="text-muted-foreground mt-1 flex flex-wrap text-xs md:text-sm">
							<span class="ml-1 line-clamp-2">
								(If the video doesn’t play, gets stuck, or fails to load, try refreshing, or copy
								the URL to play it in an external player.)
							</span>
						</CardDescription>
					</div>
				</div>

				<div class="flex items-center">
					<Button variant="outline" size="sm" onclick={clearPuppeteerProxiedUrlVideos}>
						<Trash2 class="mr-2 h-4 w-4" /> Clear
					</Button>
				</div>
			</div>
		</CardHeader>

		<CardContent>
			<div
				class="grid gap-6 {preferences.viewMode === 'grid'
					? 'grid-cols-1 md:grid-cols-2'
					: 'grid-cols-1'}"
			>
				{#each puppeteerProxiedUrlVideos as video (video.id)}
					<div class="group relative w-full overflow-hidden rounded-lg border">
						<!-- Video Player Section -->
						<div class="aspect-video overflow-hidden bg-gray-100 dark:bg-gray-800">
							<VideoPlayer
								poster={preferences.showThumbnails ? video.thumbnail : ''}
								muted={preferences.muteByDefault}
								preload={preferences.preloadMetadata ? 'metadata' : 'none'}
								qualities={[{ src: video.downloadUrl, label: video.quality || 'Default' }]}
							/>
						</div>

						<!-- Info Section -->
						<div class="flex-1 p-4">
							<div class="flex items-start justify-between gap-4">
								<div class="min-w-0 flex-1">
									<h4
										class="line-clamp-2 text-sm font-semibold text-gray-900 md:text-base dark:text-gray-100"
									>
										Proxied
									</h4>
								</div>

								<div class="flex items-center">
									<Button
										variant="ghost"
										size="sm"
										onclick={() => downloadVideo(video)}
										class="h-7 px-2"
										title="Download"
									>
										<Download class="h-4 w-4" />
									</Button>
								</div>
							</div>
						</div>
					</div>
				{/each}
			</div>
		</CardContent>
	</Card>
{/if}
