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
	import VideoPlayer from '$lib/components/VideoPlayer.svelte';
	import { appStore } from '$lib/stores/app-state.svelte';

	let { preferences } = $props();

	let ovcProxyResults = $derived(appStore.getOvcProxyResultsFromStore());

	function clearOvcProxyResultsFromStore() {
		appStore.clearOvcProxyResultsFromStore();
		toast.info('Ovc proxy videos cleared');
	}

	function downloadOvcProxyUrl(video) {
		try {
			const link = document.createElement('a');
			link.href = video.proxiedVideoUrl;
			link.download = video.id;
			link.click();
			toast.success('Download started: ' + video.id);
		} catch (error) {
			toast.error('Failed to start download: ' + String(error));
		}
	}
</script>

{#if ovcProxyResults.length > 0}
	<Card class="bg-card dark:bg-card-dark mx-auto mb-6">
		<CardHeader>
			<div class="flex items-center justify-between gap-4">
				<div>
					<CardTitle
						class="line-clamp-1 flex items-center gap-2 {preferences.enableCompact
							? 'text-sm'
							: 'text-base'}"
					>
						Ovc proxy Videos ({ovcProxyResults.length})
					</CardTitle>
					<CardDescription class="text-muted-foreground mt-1 flex flex-wrap text-xs md:text-sm">
						<span class="line-clamp-2 text-amber-500">
							(If the video doesn’t play, gets stuck, or fails to load, try refreshing, or copy the
							URL to play it in an external player.)
						</span>
					</CardDescription>
				</div>

				<div class="flex items-center">
					<Button variant="outline" size="sm" onclick={clearOvcProxyResultsFromStore}>
						<Trash2 class="mr-2 h-4 w-4" /> Clear
					</Button>
				</div>
			</div>
		</CardHeader>

		<CardContent>
			<div
				class="grid gap-6 {preferences.layoutList === 'grid'
					? 'grid-cols-1 md:grid-cols-2'
					: 'grid-cols-1'}"
			>
				{#each ovcProxyResults as video}
					<div class="group relative w-full rounded-lg border">
						<!-- Video Player Section -->
						<div class="aspect-video bg-gray-100 dark:bg-gray-800">
							<VideoPlayer
								poster={''}
								qualities={[
									{
										proxiedVideoUrl: video.proxiedVideoUrl
									}
								]}
							/>
						</div>

						<!-- Info Section -->
						<div class="flex-1 overflow-hidden p-4">
							<div class="flex items-start justify-between gap-4">
								<div class="min-w-0 flex-1">
									<h4
										class="line-clamp-2 text-sm font-semibold text-gray-900 md:text-base dark:text-gray-100"
									>
										{video.id}
									</h4>
								</div>

								<div class="flex items-center">
									<Button
										variant="ghost"
										size="sm"
										onclick={() => downloadOvcProxyUrl(video)}
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
