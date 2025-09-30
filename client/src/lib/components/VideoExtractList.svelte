<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { Button } from '$lib/components/ui/button';
	import { Switch } from '$lib/components/ui/switch';
	import { Label } from '$lib/components/ui/label';
	import {
		Card,
		CardContent,
		CardDescription,
		CardHeader,
		CardTitle
	} from '$lib/components/ui/card';
	import * as DropdownMenu from '$lib/components/ui/dropdown-menu';
	import TableProperties from 'lucide-svelte/icons/table-properties';
	import ChevronDown from 'lucide-svelte/icons/chevron-down';
	import Copy from 'lucide-svelte/icons/copy';
	import Download from 'lucide-svelte/icons/download';
	import Waypoints from 'lucide-svelte/icons/waypoints';
	import Trash2 from 'lucide-svelte/icons/trash-2';
	import Globe from 'lucide-svelte/icons/globe';
	import VideoPlayer from '$lib/components/VideoPlayer.svelte';
	import { appStore } from '$lib/stores/app-state.svelte';

	let { isOVCProxyRunning, isVideoExtractRunning, preferences, runOvcProxyFromServer } = $props();

	let isOperationRunning = $derived(isOVCProxyRunning || isVideoExtractRunning);
	let videoExtractResults = $derived(appStore.videoExtractResults);

	function formatBytesToMB(bytes: number) {
		if (!bytes || bytes <= 0) return 'Unknown';
		const mb = bytes / (1024 * 1024);
		return `${Math.round(mb * 10) / 10} MB`;
	}

	function formatSecondsToTime(seconds: number) {
		if (!seconds) return '0:00';
		const mins = Math.floor(seconds / 60);
		const secs = Math.floor(seconds % 60)
			.toString()
			.padStart(2, '0');
		return `${mins}:${secs}`;
	}

	function clearVideoExtractResults() {
		appStore.clearVideoExtractResultsFromStore();
		toast.info('extracted results cleared');
	}

	function formatYYYYMMDDToDate(yyyyMMdd: string) {
		if (!yyyyMMdd || yyyyMMdd.length < 8) return '';
		const y = parseInt(yyyyMMdd.substring(0, 4), 10);
		const m = parseInt(yyyyMMdd.substring(4, 6), 10) - 1;
		const d = parseInt(yyyyMMdd.substring(6, 8), 10);
		return new Date(y, m, d).toLocaleDateString();
	}

	function copyVideoExtractUrlToClipboard(url: string, id: string) {
		try {
			navigator.clipboard.writeText(url);
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

	function downloadVideoExtractUrl(video, qualityIndex = 0) {
		try {
			const quality = video.qualities[qualityIndex] || video.qualities[0];
			const filename = `${video?.title}.${quality.resolution}.${quality.ext}`;
			const link = document.createElement('a');
			link.href = preferences.enableProxyForVideoExtract
				? quality.proxiedVideoUrl
				: quality.sourceVideoUrl;
			link.download = filename;
			link.click();
			toast.success('Download started: ' + filename);
		} catch (error) {
			toast.error('Failed to start download: ' + String(error));
		}
	}

	function runOvcProxy(video, qualityIndex = 0) {
		try {
			toast.success('Proxy started');
			const quality = video.qualities[qualityIndex] || video.qualities[0];
			runOvcProxyFromServer(quality?.sourceVideoUrl);
		} catch (error) {
			toast.error('Failed to start proxy: ' + String(error));
		}
	}

	function toggleProxyMode() {
		appStore.updatePreferences({
			enableProxyForVideoExtract: !preferences.enableProxyForVideoExtract
		});
		toast.info(`${preferences.enableProxyForVideoExtract ? 'Disabled' : 'Enabled'} proxy mode`);
	}
</script>

{#if videoExtractResults.length > 0}
	<Card class="bg-card dark:bg-card-dark mx-auto mb-6">
		<CardHeader>
			<div class="flex items-center justify-between gap-4">
				<div class="flex items-center gap-3">
					<div>
						<CardTitle
							class="line-clamp-1 flex items-center gap-2 {preferences.enableCompact
								? 'text-sm'
								: 'text-base'}"
						>
							Media Group ({videoExtractResults.length})
						</CardTitle>
						<CardDescription
							class="text-muted-foreground mt-1 flex flex-wrap gap-2.5 text-xs md:text-sm"
						>
							<span class="line-clamp-2 text-amber-500">
								(If the video doesn’t play, gets stuck, or fails to load, try switching quality,
								refreshing, or copy the URL to play it in an external player.)
							</span>
						</CardDescription>
					</div>
				</div>

				<div class="flex items-center">
					<Button variant="outline" size="sm" onclick={clearVideoExtractResults}>
						<Trash2 class="mr-2 h-4 w-4" /> Clear
					</Button>
				</div>
			</div>
		</CardHeader>

		<CardContent>
			<div
				class="grid gap-4 {preferences.layoutList === 'grid'
					? 'grid-cols-1 lg:grid-cols-2'
					: 'grid-cols-1'}"
			>
				{#each videoExtractResults as video}
					<div
						class="group relative w-full rounded-lg border bg-white transition-shadow hover:shadow-md dark:bg-zinc-900"
					>
						<div
							class={preferences.layoutList === 'list'
								? 'flex flex-col md:flex-row'
								: 'flex flex-col'}
						>
							<div class={preferences.layoutList === 'list' ? 'w-full md:w-3/5' : 'w-full'}>
								<VideoPlayer poster={video.thumbnail} qualities={video.qualities} />
							</div>

							<!-- Info + Actions -->
							<div
								class=" overflow-hidden {preferences.enableCompact
									? 'p-3'
									: 'p-4'} flex-1 {preferences.layoutList === 'list'
									? 'flex flex-col justify-between'
									: 'flex h-full flex-col'}"
							>
								<div class={preferences.layoutList === 'list' ? '' : 'flex-1'}>
									<h4
										class="mb-3 line-clamp-2 font-semibold text-zinc-900 dark:text-zinc-100 {preferences.enableCompact
											? preferences.layoutList === 'list'
												? 'text-base'
												: 'text-sm'
											: preferences.layoutList === 'list'
												? 'text-lg'
												: 'text-base'}"
										title={video.title}
									>
										{video.title}
									</h4>

									<!-- Details block -->
									<div
										class={preferences.layoutList === 'list'
											? 'mb-3 grid grid-cols-2 gap-2 text-xs md:mb-0 md:grid-cols-1 md:gap-0 md:space-y-2.5 md:text-sm'
											: 'mb-3 grid grid-cols-2 gap-2 text-xs md:text-sm'}
									>
										<div
											class={preferences.layoutList === 'list'
												? 'md:flex md:items-center md:justify-between'
												: ''}
										>
											<span class="block text-zinc-500">Type</span>
											<span class="line-clamp-1 text-zinc-900 dark:text-zinc-100"
												>{video.type || 'Unknown'}</span
											>
										</div>

										{#if video.qualities && video.qualities.length}
											<div
												class={preferences.layoutList === 'list'
													? 'md:flex md:items-center md:justify-between'
													: ''}
											>
												<span class="block text-zinc-500">Resolution</span>
												<span class="line-clamp-1 text-zinc-900 dark:text-zinc-100">
													{video.qualities.map((q) => `${q.resolution}p`).join(', ')}
												</span>
											</div>

											{#if video.qualities.length}
												<div
													class={preferences.layoutList === 'list'
														? 'md:flex md:items-center md:justify-between'
														: ''}
												>
													<span class="block text-zinc-500">Qualities</span>
													<span class="line-clamp-1 text-zinc-900 dark:text-zinc-100"
														>{video.qualities.length}</span
													>
												</div>
											{/if}

											<div
												class={preferences.layoutList === 'list'
													? 'md:flex md:items-center md:justify-between'
													: ''}
											>
												<span class="block text-zinc-500">Size</span>
												<span class="line-clamp-1 text-zinc-900 dark:text-zinc-100">
													{video.qualities
														.filter((q) => q.filesize > 0)
														.map((q) => formatBytesToMB(q.filesize))
														.join(', ') || 'Unknown'}
												</span>
											</div>
										{/if}

										{#if video.duration}
											<div
												class={preferences.layoutList === 'list'
													? 'md:flex md:items-center md:justify-between'
													: ''}
											>
												<span class="block text-zinc-500">Duration</span>
												<span class="text-zinc-900 dark:text-zinc-100"
													>{formatSecondsToTime(video.duration)}</span
												>
											</div>
										{/if}

										{#if video.upload_date}
											<div
												class={preferences.layoutList === 'list'
													? 'md:flex md:items-center md:justify-between'
													: ''}
											>
												<span class="block text-zinc-500">Uploaded</span>
												<span class="line-clamp-1 text-zinc-900 dark:text-zinc-100"
													>{formatYYYYMMDDToDate(video.upload_date)}</span
												>
											</div>
										{/if}
									</div>
								</div>

								<!-- Actions -->
								<div
									class={preferences.layoutList === 'list'
										? 'mt-6 flex items-center gap-2 md:mt-3'
										: 'mt-auto flex items-center gap-2 pt-3'}
								>
									<div class="relative flex-1">
										<DropdownMenu.Root>
											<DropdownMenu.Trigger>
												<Button variant="outline" size="sm" class="w-full justify-between">
													<span class="flex items-center">
														<TableProperties class="mr-2 h-4 w-4" />
														Actions / Downloads
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
																for={`proxy-toggle-${preferences.layoutList}-${video.id}`}
																class="text-sm text-zinc-700 dark:text-zinc-300"
															>
																Global Proxy
															</Label>
														</div>
														<Switch
															id={`proxy-toggle-${preferences.layoutList}-${video.id}`}
															checked={preferences.enableProxyForVideoExtract}
															onCheckedChange={toggleProxyMode}
														/>
													</div>
												</div>

												<div class="max-h-78 overflow-y-auto p-3">
													<h5 class="mb-3 text-sm font-medium text-zinc-800 dark:text-zinc-200">
														Quality Options
													</h5>

													<div class="space-y-2">
														{#each video.qualities as quality, index}
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
																			? formatBytesToMB(quality.filesize)
																			: 'Unknown'}
																	</span>
																</div>

																<div class="flex items-center gap-1">
																	{#if video.type === 'video/mp4' || video.type === 'audio'}
																		<Button
																			variant="ghost"
																			size="sm"
																			onclick={() => runOvcProxy(video, index)}
																			disabled={isOperationRunning}
																			class="h-7 w-7 p-0"
																			title="Proxy"
																		>
																			<Waypoints class="h-3 w-3" />
																		</Button>
																	{/if}

																	<Button
																		variant="ghost"
																		size="sm"
																		onclick={() =>
																			copyVideoExtractUrlToClipboard(
																				preferences.enableProxyForVideoExtract
																					? quality.proxiedVideoUrl
																					: quality.sourceVideoUrl,
																				`${video.id}-${index}`
																			)}
																		class="h-7 w-7 p-0"
																		title="Copy URL"
																	>
																		<Copy class="h-3 w-3" />
																	</Button>
																	{#if !(video.type === 'application/x-mpegURL') || preferences.showHlsTypeDownloadButton}
																		<Button
																			variant="ghost"
																			size="sm"
																			onclick={() => downloadVideoExtractUrl(video, index)}
																			class="h-7 w-7 p-0"
																			title="Download"
																		>
																			<Download class="h-3 w-3" />
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
								</div>
							</div>
						</div>
					</div>
				{/each}
			</div>
		</CardContent>
	</Card>
{/if}
