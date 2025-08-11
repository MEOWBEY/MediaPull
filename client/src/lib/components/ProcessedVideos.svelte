<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';

	import Download from 'lucide-svelte/icons/download';
	import Copy from 'lucide-svelte/icons/copy';
	import Trash2 from 'lucide-svelte/icons/trash-2';

	import VideoPlayer from '$lib/components/VideoPlayer.svelte';
	import { videoStore, type ProcessedVideo } from '$lib/stores/app-state.svelte';

	let processedVideoPreviewStates = $state(new Map<string, boolean>());

	let processedVideos = $derived(videoStore.getSortedProcessedVideos());
	let preferences = $derived(videoStore.preferences);
	let hasProcessedVideos = $derived(processedVideos.length > 0);


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

	function clearProcessedVideos() {
		videoStore.clearProcessedVideos();
		processedVideoPreviewStates.clear();
		toast.info('Processed videos cleared');
	}

	function downloadVideo(video: ProcessedVideo) {
		// Always use download URL for processed videos
		window.open(video.downloadUrl, '_blank');
	}

	function copyVideoUrl(video: ProcessedVideo, id: string) {
		// Always use download URL for processed videos
		copyToClipboard(video.downloadUrl, id);
	}
</script>

{#if hasProcessedVideos}
	<Card class="mb-6 ">
		<CardHeader class={preferences.compactMode ? 'py-3' : ''}>
			<div class="flex items-center justify-between">
				<CardTitle
					class="flex items-center gap-2 {preferences.compactMode
						? 'text-xs md:text-sm'
						: 'text-base md:text-lg'}"
				>
					<Download class="h-4 w-4 shrink-0 text-green-600" />
					Processed
				</CardTitle>
				<Button variant="outline" size="sm" onclick={clearProcessedVideos} class="cursor-pointer">
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
				{#each processedVideos as video (video.id)}
					<div
						class="group relative rounded-lg border {preferences.compactMode
							? 'p-2'
							: 'p-4'} {preferences.highContrast
							? 'border-2'
							: ''} transition-all duration-200 hover:shadow-md"
					>
						<div
							class="flex items-start justify-between gap-4 {preferences.compactMode
								? 'mb-2'
								: 'mb-3'}"
						>
							<div class="flex-1 {preferences.compactMode ? 'space-y-1' : 'space-y-2'}">
								<div class="flex flex-wrap items-center gap-2">
									<Badge variant="outline">{video.quality || 'Unknown'}</Badge>

								</div>
								{#if video.title}
									<p class="line-clamp-2 text-sm font-medium text-gray-900 dark:text-gray-100">
										{video.title}
									</p>
								{/if}
								{#if video.filename}
									<p class="line-clamp-1 text-xs text-gray-600 dark:text-gray-400">
										{video.filename}
									</p>
								{/if}
							</div>

							<div class="flex gap-1.5">
								<Button
									variant="outline"
									size="icon"
									onclick={() => copyVideoUrl(video, `processed-${video.id}`)}
									data-copy-id="processed-{video.id}"
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
								src={video.downloadUrl}
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
