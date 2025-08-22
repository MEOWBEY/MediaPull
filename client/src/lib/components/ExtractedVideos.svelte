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

	import SquarePlay from 'lucide-svelte/icons/square-play';
	import TableProperties from 'lucide-svelte/icons/table-properties';
	import ChevronDown from 'lucide-svelte/icons/chevron-down';
	import Copy from 'lucide-svelte/icons/copy';
	import Download from 'lucide-svelte/icons/download';
	import Waypoints from 'lucide-svelte/icons/waypoints';
	import Loader2 from 'lucide-svelte/icons/loader-2';
	import Trash2 from 'lucide-svelte/icons/trash-2';
	import Globe from 'lucide-svelte/icons/globe';

	import VideoPlayer from '$lib/components/VideoPlayer.svelte';
	import { videoStore, type VideoFormat } from '$lib/stores/app-state.svelte';

	import { organizeVideoFormats, type OrganizedVideo } from '$lib/stores/app-state.svelte';

	interface Props {
		handlePuppeteerProxyUrlVideo: (video?: VideoFormat) => Promise<void>;
	}

	let { handlePuppeteerProxyUrlVideo }: Props = $props();

	let extractedData = $derived(videoStore.extractedData);
	let preferences = $derived(videoStore.preferences);
	let puppeteerProxyUrlQueue = $derived(videoStore.puppeteerProxyUrlQueue);
	let isOperationRunning = $derived(videoStore.puppeteerProxyingUrl || videoStore.extracting);

	let organizedVideos = $derived(organizeVideoFormats(extractedData?.formats || []));

	function clearExtractedVideos() {
		videoStore.clearExtractedData();
		toast.info('Extracted data cleared');
	}

	function getVideoUrl(quality: any): string {
		return preferences.useProxy
			? quality.downloadUrl || quality.src
			: quality.originalUrl || quality.src;
	}

	async function copyToClipboard(url: string, id: string) {
		try {
			await navigator.clipboard.writeText(url);
			toast.success('Copied URL to clipboard: ' + url);
			const element = document.querySelector(`[data-copy-id="${id}"]`);
			if (element) {
				element.classList.add('text-green-500');
				setTimeout(() => element.classList.remove('text-green-500'), 2000);
			}
		} catch (error) {
			toast.error('Failed to copy: ' + error);
		}
	}

	function downloadVideo(organized: OrganizedVideo, qualityIndex = 0) {
		try {
			const quality = organized.qualities[qualityIndex] || organized.qualities[0];
			const videoUrl = getVideoUrl(quality);
			const filename = `${organized.title}-${quality.label}`;

			const link = document.createElement('a');
			link.href = videoUrl;
			link.download = filename;
			link.click();

			toast.success('Download started: ' + filename);
		} catch (error) {
			toast.error('Failed to start download: ' + error);
		}
	}

	async function proxyVideo(organized: OrganizedVideo, qualityIndex = 0) {
		try {
			const quality = organized.qualities[qualityIndex] || organized.qualities[0];

			await handlePuppeteerProxyUrlVideo(quality);
			toast.success('Proxy started');
		} catch (error) {
			toast.error('Failed to start proxy' + error);
		}
	}

	function isVideoInProxyQueue(organized: OrganizedVideo, qualityIndex = 0): boolean {
		const quality = organized.qualities[qualityIndex] || organized.qualities[0];
		const proxyKey = `${quality.src}-${quality.resolution}`;
		return puppeteerProxyUrlQueue.has(proxyKey);
	}

	function toggleGlobalProxy() {
		videoStore.updatePreferences({ useProxy: !preferences.useProxy });
		toast.info(`${preferences.useProxy ? 'Disabled' : 'Enabled'} proxy mode`);
	}
</script>

{#if extractedData}
	<Card class="mb-6">
		<CardHeader class={preferences.compactMode ? 'border-b py-3 [.border-b]:pb-2' : ' border-b '}>
			<div class="flex items-center justify-between">
				<CardTitle
					class="flex items-center gap-2 {preferences.compactMode ? 'text-base' : 'text-lg'}"
				>
					<SquarePlay class="h-5 w-5 text-blue-600" />
					Media Formats ({organizedVideos.length})
				</CardTitle>
				<Button variant="outline" size="sm" onclick={clearExtractedVideos}>
					<Trash2 class="mr-2 h-4 w-4" />
					Clear
				</Button>
			</div>
			<CardDescription>
				{extractedData?.title || 'Media'} • {extractedData?.totalFormats} total formats
				{#if extractedData?.duration}
					• {Math.floor(extractedData.duration / 60)}:{(extractedData.duration % 60)
						.toString()
						.padStart(2, '0')}
				{/if}
			</CardDescription>
		</CardHeader>

		<CardContent class="space-y-4 ">
			<div
				class="grid {preferences.compactMode ? 'gap-2' : 'gap-4'} {preferences.viewMode === 'grid'
					? 'sm:grid-cols-2'
					: 'grid-cols-1'}"
			>
				{#each organizedVideos as organized (organized.key)}
					<div class="rounded-lg">
						<!-- Header -->
						<div class="mb-3 flex items-center justify-between gap-8">
							<div class="flex items-center gap-3">
								<div>
									<h4
										class="font-semibold text-gray-900 dark:text-gray-100 {preferences.compactMode
											? 'text-sm'
											: 'text-base'}"
									>
										{organized.type}
									</h4>
									<p class="text-sm text-gray-600 dark:text-gray-400">
										{organized.qualities.length} option{organized.qualities.length !== 1 ? 's' : ''}
									</p>
								</div>
							</div>

							<!-- Actions Dropdown -->
							<DropdownMenu.Root>
								<DropdownMenu.Trigger>
									<Button variant="outline" size="sm" class="cursor-pointer">
										<TableProperties class="mr-2 h-4 w-4" />
										Actions
										<ChevronDown class="ml-2 h-4 w-4" />
									</Button>
								</DropdownMenu.Trigger>
								<DropdownMenu.Content align="end" class="w-72">
									<!-- Global Proxy Toggle -->
									<div class="flex items-center justify-between p-2">
										<div class="flex items-center gap-2">
											<Globe class="h-4 w-4 text-gray-500" />
											<Label for="proxy-toggle" class="text-sm font-medium">Global Proxy</Label>
										</div>
										<Switch
											id="proxy-toggle"
											checked={preferences.useProxy || false}
											onCheckedChange={toggleGlobalProxy}
										/>
									</div>

									<DropdownMenu.Separator />

									<!-- Quality Options -->
									<div class="p-2">
										<h5 class="mb-2 text-sm font-medium text-gray-700 dark:text-gray-300">
											Quality Options
										</h5>
										<div class="space-y-1">
											{#each organized.qualities as quality, index}
												<div class="flex items-center justify-between rounded py-2">
													<Badge variant="outline" class="text-xs">
														{quality.label}
													</Badge>

													<div class="flex items-center gap-1">
														<!-- Proxy Button -->
														{#if organized.type === 'video' || organized.type === 'audio'}
															<Button
																variant="ghost"
																size="icon"
																onclick={() => proxyVideo(organized, index)}
																disabled={isVideoInProxyQueue(organized, index) ||
																	isOperationRunning}
																class="h-8 w-8"
																title="Proxy this quality"
															>
																{#if isVideoInProxyQueue(organized, index)}
																	<Loader2 class="h-4 w-4 animate-spin" />
																{:else}
																	<Waypoints class="h-4 w-4" />
																{/if}
															</Button>
														{/if}

														<!-- Copy Button -->
														<Button
															variant="ghost"
															size="icon"
															onclick={() =>
																copyToClipboard(getVideoUrl(quality), `${organized.key}-${index}`)}
															class="h-8 w-8"
															title="Copy URL"
															data-copy-id="{organized.key}-{index}"
														>
															<Copy class="h-4 w-4" />
														</Button>

														<!-- Download Button -->
														{#if !(organized.type === 'hls' || organized.type === 'dash') || preferences.showHlsDownloadButton}
															<Button
																variant="ghost"
																size="icon"
																onclick={() => downloadVideo(organized, index)}
																class="h-8 w-8"
																title="Download"
															>
																<Download class="h-4 w-4" />
															</Button>
														{/if}
													</div>
												</div>
											{/each}
										</div>
									</div>
								</DropdownMenu.Content>
							</DropdownMenu.Root>
						</div>

						<!-- Video Player -->
						<div class="overflow-hidden rounded-lg">
							<VideoPlayer
								poster={preferences.showThumbnails ? organized.thumbnail || '' : ''}
								muted={preferences.muteByDefault}
								preload={preferences.preloadMetadata ? 'metadata' : 'none'}
								qualities={organized.qualities}
							/>
						</div>
					</div>
				{/each}
			</div>
		</CardContent>
	</Card>
{/if}
