<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { Button } from '$lib/components/ui/button';
	import { Switch } from '$lib/components/ui/switch';
	import { Label } from '$lib/components/ui/label';
	import { Badge } from '$lib/components/ui/badge';
	import {
		Card,
		CardContent,
		CardDescription,
		CardHeader,
		CardTitle
	} from '$lib/components/ui/card';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu';

	import MonitorPlay from 'lucide-svelte/icons/monitor-play';
	import ChevronDown from 'lucide-svelte/icons/chevron-down';
	import Copy from 'lucide-svelte/icons/copy';
	import Download from 'lucide-svelte/icons/download';
	import Hammer from 'lucide-svelte/icons/hammer';
	import Loader2 from 'lucide-svelte/icons/loader-2';
	import Trash2 from 'lucide-svelte/icons/trash-2';
	import Globe from 'lucide-svelte/icons/globe';

	import VideoPlayer from '$lib/components/VideoPlayer.svelte';
	import {
		videoStore,
		organizeVideosBySourceAndType,
		type VideoFormat
	} from '$lib/stores/app-state.svelte';

	interface Props {
		handleProcessVideo: (video?: VideoFormat) => Promise<void>;
	}

	let { handleProcessVideo }: Props = $props();

	let extractedData = $derived(videoStore.extractedData);
	let preferences = $derived(videoStore.preferences);
	let processingQueue = $derived(videoStore.processingQueue);
	let isOperationRunning = $derived(videoStore.processing || videoStore.extracting);
	let hasExtractedData = $derived(extractedData !== null);
	let organizedVideos = $derived(organizeVideosBySourceAndType(extractedData?.formats || []));

	function clearExtractedVideos() {
		videoStore.clearExtractedData();
		toast.info('Extracted data cleared');
	}

	async function copyToClipboard(text: string, id: string, useProxy: boolean = false) {
		try {
			await navigator.clipboard.writeText(text);
			toast.success(`Copied ${useProxy ? 'original' : 'download'} URL to clipboard`);
			const element = document.querySelector(`[data-copy-id="${id}"]`);
			if (element) {
				element.classList.add('text-green-500');
				setTimeout(() => element.classList.remove('text-green-500'), 2000);
			}
		} catch (error) {
			toast.error('Failed to copy');
		}
	}

	function downloadVideo(video: VideoFormat, id: string) {
		try {
			const link = document.createElement('a');
			link.href = getUrlForAction(video);
			link.download = video.filename || 'video';
			link.click();
			toast.success('Download started');
			const element = document.querySelector(`[data-download-id="${id}"]`);
			if (element) {
				element.classList.add('text-green-500');
				setTimeout(() => element.classList.remove('text-green-500'), 2000);
			}
		} catch (error) {
			toast.error('Failed to start download');
		}
	}

	async function processVideoWithToast(video: VideoFormat) {
		try {
			await handleProcessVideo(video);
			toast.success('Video processing started');
		} catch (error) {
			toast.error('Failed to start processing');
		}
	}

	function isVideoProcessing(video: VideoFormat): boolean {
		const processKey = `${video.originalUrl}-${video.quality}`;
		return processingQueue.has(processKey);
	}

	function getBestQuality(typeGroup: any) {
		const resolutions = Object.entries(typeGroup.formats);
		const sortedResolutions = resolutions.sort((a, b) => {
			const aHeight = parseInt(a[0].replace('p', '')) || 0;
			const bHeight = parseInt(b[0].replace('p', '')) || 0;
			return bHeight - aHeight;
		});
		return sortedResolutions[0]?.[1] as VideoFormat;
	}

	function getVideoQualities(
		typeGroup: any
	): Array<{ src: string; label: string; resolution?: string }> {
		let qualities: any = [];

		if (!typeGroup?.formats) {
			return qualities;
		}

		Object.entries(typeGroup.formats).forEach(([resolution, format]: [string, any]) => {
			qualities.push({
				src: preferences.useProxy ? format.downloadUrl : format.originalUrl,
				label: resolution,
				resolution: format.resolution
			});
		});

		return qualities;
	}

	function getUrlForAction(video: VideoFormat): string {
		return preferences.useProxy ? video.downloadUrl : video.originalUrl;
	}

	function toggleGlobalProxy() {
		videoStore.updatePreferences({ useProxy: !preferences.useProxy });
		toast.info(`${preferences.useProxy ? 'Disabled' : 'Enabled'} proxy mode`);
	}
</script>

{#if hasExtractedData}
	<Card class="mb-6 gap-3 border shadow-sm {preferences.highContrast ? 'border-2' : ''}">
		<CardHeader class={preferences.compactMode ? 'py-3' : ''}>
			<div class="flex items-center justify-between">
				<CardTitle
					class="flex items-center gap-2 {preferences.compactMode ? 'text-base' : 'text-lg'}"
				>
					<MonitorPlay class="h-5 w-5 text-blue-600" />
					Formats
				</CardTitle>
				<Button variant="outline" size="sm" onclick={clearExtractedVideos} class="cursor-pointer">
					<Trash2 class="mr-2 h-4 w-4" />
					Clear
				</Button>
			</div>
			<CardDescription>
				{extractedData?.title || 'Video'} • {extractedData?.totalFormats} formats
				{#if extractedData?.duration}
					• {Math.floor(extractedData.duration / 60)}:{(extractedData.duration % 60)
						.toString()
						.padStart(2, '0')}
				{/if}
			</CardDescription>
		</CardHeader>
		<CardContent>
			{#each Object.entries(organizedVideos) as [groupKey, sourceGroup]}
				<div class="{preferences.compactMode ? 'mb-3' : 'mb-6'} last:mb-0">
					{#each Object.entries(sourceGroup.types) as [type, typeGroup]}
						<div
							class="rounded-lg border {preferences.compactMode
								? 'p-2'
								: 'p-4'} {preferences.highContrast ? 'border-2' : ''}"
						>
							<div
								class="flex items-center justify-between {preferences.compactMode
									? 'mb-2'
									: 'mb-3'}"
							>
								<div class="flex items-center gap-2">
									<div>
										<h4
											class="font-semibold text-gray-900 capitalize dark:text-gray-100 {preferences.compactMode
												? 'text-xs md:text-sm'
												: 'text-sm md:text-lg'}"
										>
											{type} Formats
										</h4>
										<p
											class="text-gray-600 dark:text-gray-400 {preferences.compactMode
												? 'text-xs'
												: 'text-sm'}"
										>
											{Object.keys(typeGroup.formats).length} options
										</p>
									</div>
								</div>
								<div class="flex items-center gap-2">
									<DropdownMenu.Root>
										<DropdownMenu.Trigger>
											<Button
												variant="outline"
												size="sm"
												class="cursor-pointer text-sm md:text-base"
											>
												<MonitorPlay class="mr-1 h-4 w-4 md:mr-2" />
												Options
												<ChevronDown class="ml-1 h-4 w-4 md:ml-2" />
											</Button>
										</DropdownMenu.Trigger>
										<DropdownMenu.Content align="end" class="w-64 rounded-md p-2 shadow-lg ">
											<div
												class="flex items-center justify-between rounded-md px-2 py-2 transition-colors"
											>
												<div class="flex items-center gap-2">
													<Globe class="h-4 w-4 text-gray-500 dark:text-gray-400" />
													<Label
														for="proxy-global"
														class="cursor-pointer text-sm font-medium text-gray-700 dark:text-gray-200"
													>
														Proxy
													</Label>
												</div>
												<Switch
													id="proxy-global"
													checked={preferences.useProxy || false}
													onCheckedChange={toggleGlobalProxy}
													class=""
												/>
											</div>

											<!-- Quality Options Section -->
											<DropdownMenu.Separator class="my-1 border-gray-200 dark:border-gray-600" />

											<div class="space-y-1">
												{#each Object.entries(typeGroup.formats) as [resolution, video]}
													<div
														class="flex items-center justify-between rounded-md px-2 py-2 transition-colors hover:bg-gray-100 dark:hover:bg-gray-600/50"
													>
														<div class="flex items-center gap-2">
															<Badge
																variant="outline"
																class="border-gray-300 text-xs font-medium text-gray-700 dark:border-gray-600 dark:text-gray-200"
															>
																{resolution}
															</Badge>

															{#if video.fps}
																<span class="text-xs text-gray-500 dark:text-gray-400">
																	{video.fps}fps
																</span>
															{/if}
														</div>
														<div class="flex items-center gap-1">
															{#if !video.isHLS && type !== 'hls' && type !== 'dash'}
																<Button
																	variant="ghost"
																	size="icon"
																	onclick={() => processVideoWithToast(video)}
																	disabled={isVideoProcessing(video) || isOperationRunning}
																	class="h-8 w-8 text-gray-500 transition-colors hover:bg-gray-200 hover:text-green-500 dark:text-gray-400 dark:hover:bg-gray-600 dark:hover:text-green-400"
																	aria-label="Process video"
																>
																	{#if isVideoProcessing(video)}
																		<Loader2 class="h-4 w-4 animate-spin" />
																	{:else}
																		<Hammer class="h-4 w-4" />
																	{/if}
																</Button>
															{/if}
															<Button
																variant="ghost"
																size="icon"
																onclick={() =>
																	copyToClipboard(
																		getUrlForAction(video),
																		`${groupKey}-${type}-${resolution}`,
																		preferences.useProxy
																	)}
																class="h-8 w-8 text-gray-500 transition-colors hover:bg-gray-200 hover:text-green-500 dark:text-gray-400 dark:hover:bg-gray-600 dark:hover:text-green-400"
																aria-label="Copy video URL"
																data-copy-id="{groupKey}-{type}-{resolution}"
															>
																<Copy class="h-4 w-4" />
															</Button>
															{#if (!video.isHLS && type !== 'hls' && type !== 'dash') || preferences.showHlsDownloadButton}
																<Button
																	variant="ghost"
																	size="icon"
																	onclick={() =>
																		downloadVideo(video, `${groupKey}-${type}-${resolution}`)}
																	class="h-8 w-8 text-gray-500 transition-colors hover:bg-gray-200 hover:text-green-500 dark:text-gray-400 dark:hover:bg-gray-600 dark:hover:text-green-400"
																	aria-label="Download video"
																	data-download-id="{groupKey}-{type}-{resolution}"
																>
																	<Download class="h-4 w-4" />
																</Button>
															{/if}
														</div>
													</div>
												{/each}
											</div>
										</DropdownMenu.Content>
									</DropdownMenu.Root>
								</div>
							</div>
							{#if getBestQuality(typeGroup)}
								<div class="overflow-hidden">
									<VideoPlayer
										src={getUrlForAction(getBestQuality(typeGroup))}
										poster={preferences.showThumbnails ? getBestQuality(typeGroup)?.thumbnail : ''}
										muted={preferences.muteByDefault}
										preload={preferences.preloadMetadata ? 'metadata' : 'none'}
										qualities={getVideoQualities(typeGroup)}
									/>
								</div>
							{/if}
						</div>
					{/each}
				</div>
			{/each}
		</CardContent>
	</Card>
{/if}
