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
	import * as Separator from '$lib/components/ui/separator';
	import Film from 'lucide-svelte/icons/film';
	import FileText from 'lucide-svelte/icons/file-text';
	import TvMinimal from 'lucide-svelte/icons/tv-minimal';
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

	let organizedVideos = $derived(
		organizeVideoFormats(extractedData?.formats, extractedData?.metadata)
	);

	function formatFileSizeMB(bytes: number) {
		if (!bytes || bytes <= 0) return 'Unknown';
		const mb = bytes / (1024 * 1024);
		return `${Math.round(mb * 10) / 10} MB`;
	}
	function formatDuration(seconds: number) {
		if (!seconds) return '0:00';
		const mins = Math.floor(seconds / 60);
		const secs = Math.floor(seconds % 60)
			.toString()
			.padStart(2, '0');
		return `${mins}:${secs}`;
	}

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
			toast.success('Copied URL to clipboard');
			const element = document.querySelector(`[data-copy-id="${id}"]`);
			if (element) {
				element.classList.add('text-green-500');
				setTimeout(() => element.classList.remove('text-green-500'), 2000);
			}
		} catch (error) {
			toast.error('Failed to copy: ' + String(error));
		}
	}

	function downloadVideo(organized: OrganizedVideo, qualityIndex = 0) {
		try {
			const quality = organized.qualities[qualityIndex] || organized.qualities[0];
			const videoUrl = getVideoUrl(quality);
			const filename = `${organized?.title}.${quality.resolution}.${quality.ext}`;
			const link = document.createElement('a');
			link.href = videoUrl;
			link.download = filename;
			link.click();
			toast.success('Download started: ' + filename);
		} catch (error) {
			toast.error('Failed to start download: ' + String(error));
		}
	}

	async function proxyVideo(organized: OrganizedVideo, qualityIndex = 0) {
		try {
			const quality = organized.qualities[qualityIndex] || organized.qualities[0];
			await handlePuppeteerProxyUrlVideo(quality);
			toast.success('Proxy started');
		} catch (error) {
			toast.error('Failed to start proxy: ' + String(error));
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
	const formatUploadDate = (yyyyMMdd: string) => {
		if (!yyyyMMdd || yyyyMMdd.length < 8) return '';
		const y = parseInt(yyyyMMdd.substring(0, 4), 10);
		const m = parseInt(yyyyMMdd.substring(4, 6), 10) - 1;
		const d = parseInt(yyyyMMdd.substring(6, 8), 10);
		return new Date(y, m, d).toLocaleDateString();
	};
</script>

{#if extractedData}
	<Card class="bg-card dark:bg-card-dark mx-auto mb-6">
		<CardHeader>
			<div class="flex items-center justify-between gap-4">
				<div class="flex min-w-0 items-center gap-3">
					<span
						class="flex items-center justify-center rounded-full bg-gray-200 p-3 dark:bg-zinc-800"
					>
						<TvMinimal class="h-5 w-5 shrink-0 text-amber-600" />
					</span>

					<div class="min-w-0">
						<CardTitle
							class="line-clamp-1 flex items-center gap-2 {preferences.compactMode
								? 'text-sm'
								: 'text-base'}"
						>
							Media Formats ({organizedVideos.length})
						</CardTitle>
						<CardDescription
							class="text-muted-foreground mt-1 flex flex-wrap gap-1.5 text-xs md:text-sm"
						>
							<span class="ml-1">
								Video • {extractedData?.totalFormats ?? 0} formats
							</span>
							<span class=" line-clamp-2">
								(If the video doesn’t play, gets stuck, or fails to load, try switching quality,
								refreshing, or copy the URL to play it in an external player.)
							</span>
						</CardDescription>
					</div>
				</div>

				<div class="flex items-center">
					<Button variant="outline" size="sm" onclick={clearExtractedVideos}>
						<Trash2 class="mr-2 h-4 w-4" /> Clear
					</Button>
				</div>
			</div>
		</CardHeader>

		<CardContent>
			<div
				class="grid gap-4 {preferences.viewMode === 'grid'
					? 'grid-cols-1 lg:grid-cols-2'
					: 'grid-cols-1'}"
			>
				{#each organizedVideos as organized (organized.key)}
					<div
						class="group relative w-full overflow-hidden rounded-lg border bg-white transition-shadow hover:shadow-md dark:bg-zinc-900"
					>
						{#if preferences.viewMode === 'list'}
							<!-- LIST VIEW -->
							<div class="flex flex-col md:flex-row">
								<!-- Video Player -->
								<div class="w-full md:w-3/5">
									<VideoPlayer
										poster={preferences.showThumbnails ? organized.thumbnail || '' : ''}
										muted={preferences.muteByDefault}
										preload={preferences.preloadMetadata ? 'metadata' : 'none'}
										qualities={organized.qualities}
									/>
								</div>

								<!-- Info Panel -->
								<div
									class="flex-1 {preferences.compactMode
										? 'p-3'
										: 'p-4'} flex flex-col justify-between"
								>
									<div>
										<h4
											class="line-clamp-2 font-semibold {preferences.compactMode
												? 'text-base'
												: 'text-lg'} mb-6 text-zinc-900 dark:text-zinc-100"
											title={organized.title}
										>
											{organized.title}
										</h4>

										<div class="space-y-4 text-sm">
											<div class="flex justify-between">
												<span class="text-zinc-500">Type</span>
												<span class="line-clamp-1 text-zinc-900 dark:text-zinc-100"
													>{organized.type || 'Unknown'}</span
												>
											</div>

											{#if organized.qualities && organized.qualities.length}
												<div class="flex justify-between">
													<span class="text-zinc-500">Resolution</span>
													<span class="line-clamp-1 text-zinc-900 dark:text-zinc-100">
														{organized.qualities.map((q) => `${q.resolution}p`).join(', ')}
													</span>
												</div>

												<div class="flex justify-between">
													<span class="text-zinc-500">Size</span>
													<span class="line-clamp-1 text-zinc-900 dark:text-zinc-100">
														{organized.qualities
															.filter((q) => q.filesize > 0)
															.map((q) => formatFileSizeMB(q.filesize))
															.join(', ') || 'Unknown'}
													</span>
												</div>
											{/if}

											{#if organized.duration}
												<div class="flex justify-between">
													<span class="text-zinc-500">Duration</span>
													<span class="text-zinc-900 dark:text-zinc-100"
														>{formatDuration(organized.duration)}</span
													>
												</div>
											{/if}

											{#if organized.upload_date}
												<div class="flex justify-between">
													<span class="text-zinc-500">Uploaded</span>
													<span class="line-clamp-1 text-zinc-900 dark:text-zinc-100"
														>{formatUploadDate(organized.upload_date)}</span
													>
												</div>
											{/if}
										</div>
									</div>

									<!-- Actions -->
									<div class="mt-6 flex items-center gap-2 md:mt-3">
										<div class="relative flex-1">
											<DropdownMenu.Root>
												<DropdownMenu.Trigger>
													<Button variant="outline" size="sm" class="w-full justify-between">
														<span class="flex items-center">
															<TableProperties class="mr-2 h-4 w-4" />
															Actions
														</span>
														<ChevronDown class="h-4 w-4" />
													</Button>
												</DropdownMenu.Trigger>

												<DropdownMenu.Content
													align="start"
													side="bottom"
													sideOffset={5}
													class="w-80"
													avoidCollisions={true}
													sticky="always"
												>
													<div class="bg-zinc-50 p-3 dark:bg-zinc-800">
														<div class="flex items-center justify-between">
															<div class="flex items-center gap-2">
																<Globe class="h-4 w-4 text-zinc-600" />
																<Label
																	for="proxy-toggle-list"
																	class="text-sm text-zinc-700 dark:text-zinc-300"
																>
																	Global Proxy
																</Label>
															</div>
															<Switch
																id="proxy-toggle-list"
																checked={preferences.useProxy || false}
																onchange={toggleGlobalProxy}
															/>
														</div>
													</div>

													<div class="max-h-78 overflow-y-auto p-3">
														<h5 class="mb-3 text-sm font-medium text-zinc-800 dark:text-zinc-200">
															Quality Options
														</h5>

														<div class="space-y-2">
															{#each organized.qualities as quality, index}
																<div
																	class="flex items-center justify-between rounded bg-zinc-50 p-2 dark:bg-zinc-800"
																>
																	<div class="flex min-w-0 items-center gap-2">
																		<span
																			class="rounded bg-zinc-200 px-2 py-1 text-xs font-medium md:text-sm dark:bg-zinc-700"
																		>
																			{`${quality.resolution}p`}
																		</span>
																		<span class="line-clamp-1 text-xs text-zinc-500">
																			{quality.filesize > 0
																				? formatFileSizeMB(quality.filesize)
																				: 'Unknown'}
																		</span>
																	</div>

																	<div class="flex items-center gap-1">
																		{#if organized.type === 'video/mp4' || organized.type === 'audio'}
																			<Button
																				variant="ghost"
																				size="sm"
																				onclick={() => proxyVideo(organized, index)}
																				disabled={isVideoInProxyQueue(organized, index) ||
																					isOperationRunning}
																				class="h-7 w-7 p-0"
																				title="Proxy"
																			>
																				{#if isVideoInProxyQueue(organized, index)}
																					<Loader2 class="h-3 w-3 animate-spin" />
																				{:else}
																					<Waypoints class="h-3 w-3" />
																				{/if}
																			</Button>
																		{/if}

																		<Button
																			variant="ghost"
																			size="sm"
																			onclick={() =>
																				copyToClipboard(
																					getVideoUrl(quality),
																					`${organized.key}-${index}`
																				)}
																			class="h-7 w-7 p-0"
																			title="Copy URL"
																		>
																			<Copy class="h-3 w-3" />
																		</Button>

																		<Button
																			variant="ghost"
																			size="sm"
																			onclick={() => downloadVideo(organized, index)}
																			class="h-7 w-7 p-0"
																			title="Download"
																		>
																			<Download class="h-3 w-3" />
																		</Button>
																	</div>
																</div>
															{/each}
														</div>
													</div>
												</DropdownMenu.Content>
											</DropdownMenu.Root>
										</div>

										<Button
											variant="ghost"
											size="sm"
											onclick={() =>
												copyToClipboard(
													getVideoUrl(organized.qualities[0] || {}),
													`${organized.key}-0`
												)}
											class="h-8 w-8 p-0"
											title="Copy URL"
										>
											<Copy class="h-4 w-4" />
										</Button>

										<Button
											variant="ghost"
											size="sm"
											onclick={() => downloadVideo(organized, 0)}
											class="h-8 w-8 p-0"
											title="Download"
										>
											<Download class="h-4 w-4" />
										</Button>
									</div>
								</div>
							</div>
						{:else}
							<!-- GRID VIEW -->
							<div class="flex flex-col">
								<!-- Video Player -->
								<div class="w-full">
									<div class="w-full overflow-hidden">
										<VideoPlayer
											poster={preferences.showThumbnails ? organized.thumbnail || '' : ''}
											muted={preferences.muteByDefault}
											preload={preferences.preloadMetadata ? 'metadata' : 'none'}
											qualities={organized.qualities}
										/>
									</div>
								</div>

								<!-- Info Panel -->
								<div class="{preferences.compactMode ? 'p-3' : 'p-4'} flex h-full flex-col">
									<div class="flex-1">
										<h4
											class="line-clamp-2 font-semibold {preferences.compactMode
												? 'text-sm'
												: 'text-base'} mb-3 text-zinc-900 dark:text-zinc-100"
											title={organized.title}
										>
											{organized.title}
										</h4>

										<div class="mb-3 grid grid-cols-2 gap-2 text-xs">
											<div>
												<span class="block text-zinc-500">Type</span>
												<span class="line-clamp-1 text-zinc-900 dark:text-zinc-100"
													>{organized.type || 'Unknown'}</span
												>
											</div>

											{#if organized.qualities && organized.qualities.length}
												<div>
													<span class="block text-zinc-500">Resolution</span>
													<span class="line-clamp-1 text-zinc-900 dark:text-zinc-100">
														{organized.qualities.map((q) => `${q.resolution}p`).join(', ')}
													</span>
												</div>
												{#if organized.qualities.length}
													<div>
														<span class="block text-zinc-500">Qualities </span>
														<span class="line-clamp-1 text-zinc-900 dark:text-zinc-100"
															>{organized.qualities.length}</span
														>
													</div>
												{/if}
												<div>
													<span class="block text-zinc-500">Size</span>
													<span class="line-clamp-1 text-zinc-900 dark:text-zinc-100">
														{organized.qualities
															.filter((q) => q.filesize > 0)
															.map((q) => formatFileSizeMB(q.filesize))
															.join(', ') || 'Unknown'}
													</span>
												</div>
											{/if}

											{#if organized.duration}
												<div>
													<span class="block text-zinc-500">Duration</span>
													<span class="text-zinc-900 dark:text-zinc-100"
														>{formatDuration(organized.duration)}</span
													>
												</div>
											{/if}
											{#if organized.upload_date}
												<div>
													<span class="block text-zinc-500">Uploaded</span>
													<span class="line-clamp-1 text-zinc-900 dark:text-zinc-100"
														>{formatUploadDate(organized.upload_date)}</span
													>
												</div>
											{/if}
										</div>
									</div>

									<!-- Actions - Always at bottom -->
									<div class="mt-auto flex items-center gap-2 pt-3">
										<div class="relative flex-1">
											<DropdownMenu.Root>
												<DropdownMenu.Trigger>
													<Button variant="outline" size="sm" class="w-full justify-between">
														<span class="flex items-center">
															<TableProperties class="mr-2 h-4 w-4" />
															Actions
														</span>
														<ChevronDown class="h-4 w-4" />
													</Button>
												</DropdownMenu.Trigger>

												<DropdownMenu.Content
													align="center"
													side="top"
													sideOffset={5}
													class="w-68"
													avoidCollisions={true}
													sticky="always"
												>
													<div class="bg-zinc-50 p-3 dark:bg-zinc-800">
														<div class="flex items-center justify-between">
															<div class="flex items-center gap-2">
																<Globe class="h-4 w-4 text-zinc-600" />
																<Label
																	for="proxy-toggle-grid"
																	class="text-sm text-zinc-700 dark:text-zinc-300"
																>
																	Global Proxy
																</Label>
															</div>
															<Switch
																id="proxy-toggle-grid"
																checked={preferences.useProxy || false}
																onchange={toggleGlobalProxy}
															/>
														</div>
													</div>

													<div class="max-h-78 overflow-y-auto p-3">
														<h5 class="mb-3 text-sm font-medium text-zinc-800 dark:text-zinc-200">
															Quality Options
														</h5>

														<div class="space-y-2">
															{#each organized.qualities as quality, index}
																<div
																	class="flex items-center justify-between rounded bg-zinc-50 p-2 dark:bg-zinc-800"
																>
																	<div class="flex min-w-0 items-center gap-2">
																		<span
																			class="rounded bg-zinc-200 px-2 py-1 text-xs font-medium md:text-sm dark:bg-zinc-700"
																		>
																			{`${quality.resolution}p`}
																		</span>
																		<span class="line-clamp-1 text-xs text-zinc-500">
																			{quality.filesize > 0
																				? formatFileSizeMB(quality.filesize)
																				: 'Unknown'}
																		</span>
																	</div>

																	<div class="flex items-center gap-1">
																		{#if organized.type === 'video/mp4' || organized.type === 'audio'}
																			<Button
																				variant="ghost"
																				size="sm"
																				onclick={() => proxyVideo(organized, index)}
																				disabled={isVideoInProxyQueue(organized, index) ||
																					isOperationRunning}
																				class="h-7 w-7 p-0"
																				title="Proxy"
																			>
																				{#if isVideoInProxyQueue(organized, index)}
																					<Loader2 class="h-3 w-3 animate-spin" />
																				{:else}
																					<Waypoints class="h-3 w-3" />
																				{/if}
																			</Button>
																		{/if}

																		<Button
																			variant="ghost"
																			size="sm"
																			onclick={() =>
																				copyToClipboard(
																					getVideoUrl(quality),
																					`${organized.key}-${index}`
																				)}
																			class="h-7 w-7 p-0"
																			title="Copy URL"
																		>
																			<Copy class="h-3 w-3" />
																		</Button>

																		<Button
																			variant="ghost"
																			size="sm"
																			onclick={() => downloadVideo(organized, index)}
																			class="h-7 w-7 p-0"
																			title="Download"
																		>
																			<Download class="h-3 w-3" />
																		</Button>
																	</div>
																</div>
															{/each}
														</div>
													</div>
												</DropdownMenu.Content>
											</DropdownMenu.Root>
										</div>

										<Button
											variant="ghost"
											size="sm"
											onclick={() =>
												copyToClipboard(
													getVideoUrl(organized.qualities[0] || {}),
													`${organized.key}-0`
												)}
											class="h-8 w-8 p-0"
											title="Copy URL"
										>
											<Copy class="h-4 w-4" />
										</Button>

										<Button
											variant="ghost"
											size="sm"
											onclick={() => downloadVideo(organized, 0)}
											class="h-8 w-8 p-0"
											title="Download"
										>
											<Download class="h-4 w-4" />
										</Button>
									</div>
								</div>
							</div>
						{/if}
					</div>
				{/each}
			</div>
		</CardContent>
	</Card>
{/if}
