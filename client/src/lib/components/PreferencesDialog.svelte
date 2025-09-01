<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { Button } from '$lib/components/ui/button';
	import { Switch } from '$lib/components/ui/switch';
	import { Label } from '$lib/components/ui/label';
	import * as Dialog from '$lib/components/ui/dialog';
	import Monitor from 'lucide-svelte/icons/monitor';
	import Volume2 from 'lucide-svelte/icons/volume-2';
	import Palette from 'lucide-svelte/icons/palette';
	import HardDrive from 'lucide-svelte/icons/hard-drive';
	import Trash2 from 'lucide-svelte/icons/trash-2';
	import AlertCircle from 'lucide-svelte/icons/alert-circle';
	import LayoutList from 'lucide-svelte/icons/layout-list';
	import SortAsc from 'lucide-svelte/icons/sort-asc';
	import Grid3X3 from 'lucide-svelte/icons/grid-3x3';
	import Globe from 'lucide-svelte/icons/globe';
	import Info from 'lucide-svelte/icons/info';

	import { appStore } from '$lib/stores/app-state.svelte';

	let { preferences, isPreferencesDialogOpen = $bindable() } = $props();

	const sections = [
		{
			title: 'Interface',
			icon: Monitor,
			color: 'text-blue-600',
			settings: [
				{
					id: 'show-thumbnails',
					label: 'Show thumbnails',
					key: 'showVideoThumbnail',
					description: 'Display thumbnail images for videos in the list'
				},
				{
					id: 'animations-enabled',
					label: 'Enable animations',
					key: 'enableAnimations',
					description: 'Enable smooth animations and transitions throughout the interface'
				},
				{
					id: 'compact-mode',
					label: 'Compact mode',
					key: 'enableCompact',
					description: 'Use a more compact layout to fit more content on screen'
				},
				{
					id: 'high-contrast',
					label: 'High contrast',
					key: 'enableHighContrast',
					description: 'Use high contrast colors for better accessibility'
				}
			]
		},
		{
			title: 'Playback',
			icon: Volume2,
			color: 'text-green-600',
			settings: [
				{
					id: 'mute-by-default',
					label: 'Mute by default',
					key: 'enableVideoMute',
					description: 'Start videos with audio muted'
				},
				{
					id: 'preload-metadata',
					label: 'Preload metadata',
					key: 'enableVideoPreloadMetadata',
					defaultTrue: true,
					description: 'Load video metadata in advance for faster playback initialization'
				}
			]
		},
		{
			title: 'Proxy & URLs',
			icon: Globe,
			color: 'text-cyan-600',
			settings: [
				{
					id: 'use-proxy',
					label: 'proxy mode',
					key: 'enableProxyForVideoExtract',
					defaultTrue: true,
					description: 'Use proxy mode to access video URLs when direct access is blocked'
				},
				{
					id: 'show-hls-download-button',
					label: 'Show HLS download',
					key: 'showHlsTypeDownloadButton',
					description: 'Display download button for HLS (HTTP Live Streaming) videos'
				}
			]
		}
	];

	function resetToDefaults() {
		appStore.updatePreferences({
			theme: 'system',
			layoutList: 'grid',
			videoSortField: 'quality',
			videoSortOrder: 'desc',
			showVideoThumbnail: true,
			enableAnimations: true,
			enableCompact: false,
			enableVideoMute: true,
			enableVideoPreloadMetadata: false,
			enableProxyForVideoExtract: true,
			showHlsTypeDownloadButton: false,
			enableHighContrast: false
		});
		toast.success('Preferences reset to defaults');
	}

	function clearAllData() {
		appStore.reset();
		toast.success('All data cleared');
	}
</script>

<Dialog.Root bind:open={isPreferencesDialogOpen}>
	<Dialog.Content
		class="!z-[999999] m-2 mx-auto h-[90vh] overflow-auto p-3 sm:m-4 sm:h-full sm:max-w-2xl sm:p-6"
	>
		<Dialog.Header class="text-left">
			<Dialog.Title class="text-lg font-bold sm:text-xl">Preferences</Dialog.Title>
			<Dialog.Description class="text-sm text-zinc-600 dark:text-zinc-400">
				Customize your video isOVCProxyRunning experience
			</Dialog.Description>
		</Dialog.Header>

		<div class="space-y-4 pb-4 sm:space-y-8 sm:pb-6">
			{#each sections as section}
				<section class="rounded-lg border bg-white dark:border-zinc-700 dark:bg-zinc-800/50">
					<!-- Section Content -->
					<div class="p-3 sm:p-4">
						<div class="grid grid-cols-1 gap-3 sm:grid-cols-2 sm:gap-4">
							{#each section.settings as setting}
								<div
									class="flex items-start justify-between rounded-lg bg-zinc-50 p-3 transition-colors hover:bg-zinc-100 dark:bg-zinc-800/50 dark:hover:bg-zinc-800"
								>
									<div class="flex-1 pr-3">
										<div class="flex items-center gap-2">
											<Label for={setting.id} class="cursor-pointer text-sm font-medium">
												{setting.label}
											</Label>
											{#if setting.description}
												<button
													type="button"
													title={setting.description}
													class="text-zinc-400 transition-colors hover:text-zinc-600 dark:text-zinc-500 dark:hover:text-zinc-300"
												>
													<Info class="h-3 w-3" />
												</button>
											{/if}
										</div>
										{#if setting.description}
											<p class="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
												{setting.description}
											</p>
										{/if}
									</div>
									<Switch
										id={setting.id}
										checked={setting.defaultTrue
											? (preferences as any)[setting.key] !== false
											: (preferences as any)[setting.key] || false}
										onCheckedChange={(checked) =>
											appStore.updatePreferences({ [setting.key]: checked })}
									/>
								</div>
							{/each}
						</div>
					</div>
				</section>
			{/each}

			<!-- View Mode Section -->
			<section class="rounded-lg border bg-white dark:border-zinc-700 dark:bg-zinc-800/50">
				<div class="border-b p-3 dark:border-zinc-700">
					<h4 class="flex items-center gap-2 text-base font-semibold">
						<LayoutList class="h-4 w-4 text-purple-600" />
						View Mode In Desktop
					</h4>
				</div>
				<div class="p-3 sm:p-4">
					<div class="flex flex-col gap-2 sm:flex-row">
						<Button
							variant={preferences.layoutList === 'grid' ? 'default' : 'outline'}
							size="sm"
							onclick={() => appStore.updatePreferences({ layoutList: 'grid' })}
							class="flex-1 cursor-pointer justify-center p-1 px-2 sm:flex-none sm:justify-start"
						>
							<Grid3X3 class="mr-2 h-4 w-4" />
							Grid View
						</Button>
						<Button
							variant={preferences.layoutList === 'list' ? 'default' : 'outline'}
							size="sm"
							onclick={() => appStore.updatePreferences({ layoutList: 'list' })}
							class="flex-1 cursor-pointer justify-center p-1 px-2 sm:flex-none sm:justify-start"
						>
							<LayoutList class="mr-2 h-4 w-4" />
							List View
						</Button>
					</div>
				</div>
			</section>
			<!-- Sorting Options Section -->
			<section class="rounded-lg border bg-white dark:border-zinc-700 dark:bg-zinc-800/50">
				<div class="border-b p-3 dark:border-zinc-700">
					<h4 class="flex items-center gap-2 text-base font-semibold">
						<SortAsc class="h-4 w-4 text-orange-600" />
						Sorting Options
					</h4>
				</div>
				<div class="p-3 sm:p-4">
					<div class="space-y-4">
						<!-- Sort By -->
						<div class="space-y-2">
							<Label class="text-sm font-medium">Sort by</Label>
							<div class="flex flex-col gap-2 sm:flex-row">
								{#each ['name', 'size', 'quality'] as const as sortOption}
									<Button
										variant={preferences.videoSortField === sortOption ? 'default' : 'outline'}
										size="sm"
										onclick={() =>
											appStore.updatePreferences({
												videoSortField: sortOption
											})}
										class="flex-1 cursor-pointer justify-center p-1 px-2 sm:flex-none sm:justify-start"
									>
										{sortOption.charAt(0).toUpperCase() + sortOption.slice(1)}
									</Button>
								{/each}
							</div>
						</div>

						<!-- Sort Order -->
						<div class="space-y-2">
							<Label class="text-sm font-medium">Sort order</Label>
							<div class="flex flex-col gap-2 sm:flex-row">
								<Button
									variant={preferences.videoSortOrder === 'asc' ? 'default' : 'outline'}
									size="sm"
									onclick={() => appStore.updatePreferences({ videoSortOrder: 'asc' })}
									class="flex-1 cursor-pointer justify-center p-1 px-2 sm:flex-none sm:justify-start"
								>
									Ascending
								</Button>
								<Button
									variant={preferences.videoSortOrder === 'desc' ? 'default' : 'outline'}
									size="sm"
									onclick={() => appStore.updatePreferences({ videoSortOrder: 'desc' })}
									class="flex-1 cursor-pointer justify-center p-1  px-2 sm:flex-none sm:justify-start"
								>
									Descending
								</Button>
							</div>
						</div>
					</div>
				</div>
			</section>

			<!-- Theme Selection -->
			<section class="rounded-lg border bg-white dark:border-zinc-700 dark:bg-zinc-800/50">
				<div class="border-b p-3 dark:border-zinc-700">
					<h4 class="flex items-center gap-2 text-base font-semibold">
						<Palette class="h-4 w-4 text-pink-600" />
						Theme Selection
					</h4>
				</div>
				<div class="p-3 sm:p-4">
					<div class="space-y-2">
						<Label class="text-sm font-medium">Theme</Label>
						<div class="flex flex-col gap-2 sm:flex-row">
							{#each ['light', 'dark', 'system'] as const as theme}
								<Button
									variant={preferences.theme === theme ? 'default' : 'outline'}
									size="sm"
									onclick={() => appStore.updatePreferences({ theme })}
									class="flex-1 cursor-pointer justify-center p-1 px-2 sm:flex-none sm:justify-start"
								>
									{theme.charAt(0).toUpperCase() + theme.slice(1)}
								</Button>
							{/each}
						</div>
					</div>
				</div>
			</section>

			<!-- Cache & Store Section -->
			<section class="rounded-lg border bg-white dark:border-zinc-700 dark:bg-zinc-800/50">
				<div class="border-b p-3 dark:border-zinc-700">
					<h4 class="flex items-center gap-2 text-base font-semibold">
						<HardDrive class="h-4 w-4 text-red-600" />
						Cache & Store
					</h4>
				</div>
				<div class="p-3 sm:p-4">
					<div class="space-y-4">
						<!-- Stats Cards -->
						<div class="grid grid-cols-1 gap-3 sm:grid-cols-2 sm:gap-4">
							<div
								class="rounded-lg border border-blue-200 bg-gradient-to-br from-blue-50 to-blue-100 p-3 text-center sm:p-4 dark:border-blue-800 dark:from-blue-900/20 dark:to-blue-800/20"
							>
								<div class="text-xl font-bold text-blue-700 sm:text-3xl dark:text-blue-300">
									{appStore.getStats().size}
								</div>
								<div class="text-xs font-medium text-blue-600 sm:text-sm dark:text-blue-400">
									Cached Items
								</div>
							</div>
							<div
								class="rounded-lg border border-green-200 bg-gradient-to-br from-green-50 to-green-100 p-3 text-center sm:p-4 dark:border-green-800 dark:from-green-900/20 dark:to-green-800/20"
							>
								<div class="text-xl font-bold text-green-700 sm:text-3xl dark:text-green-300">
									{Math.round(appStore.getStats().hitRate)}%
								</div>
								<div class="text-xs font-medium text-green-600 sm:text-sm dark:text-green-400">
									Hit Rate
								</div>
							</div>
						</div>

						<Button
							variant="outline"
							size="sm"
							onclick={() => {
								appStore.reset();
								toast.success('Cache cleared successfully');
							}}
							class="w-full cursor-pointer p-1 px-2 transition-colors hover:border-red-300 hover:bg-red-50 hover:text-red-700 dark:hover:border-red-700 dark:hover:bg-red-900/10 dark:hover:text-red-400"
						>
							<Trash2 class="mr-2 h-4 w-4" />
							Clear All Cache
						</Button>
					</div>
				</div>
			</section>

			<!-- Reset Section -->
			<section class="rounded-lg border bg-white dark:border-zinc-700 dark:bg-zinc-800/50">
				<div class="border-b p-3 dark:border-zinc-700">
					<h4 class="flex items-center gap-2 text-base font-semibold">
						<AlertCircle class="h-4 w-4 text-red-600" />
						Reset & Defaults
					</h4>
				</div>
				<div class="p-3 sm:p-4">
					<div class="flex flex-col gap-3 sm:flex-row sm:gap-4">
						<Button variant="outline" onclick={resetToDefaults} class="flex-1 cursor-pointer">
							Reset to Defaults
						</Button>
						<Button variant="destructive" onclick={clearAllData} class="flex-1 cursor-pointer">
							<Trash2 class="mr-2 h-4 w-4" />
							Clear All Data
						</Button>
					</div>
				</div>
			</section>
		</div>
	</Dialog.Content>
</Dialog.Root>
