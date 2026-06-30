<script lang="ts">
	import AlertCircle from '@lucide/svelte/icons/alert-circle';
	import Grid3X3 from '@lucide/svelte/icons/grid-3x3';
	import HardDrive from '@lucide/svelte/icons/hard-drive';
	import Info from '@lucide/svelte/icons/info';
	import LayoutList from '@lucide/svelte/icons/layout-list';
	import Monitor from '@lucide/svelte/icons/monitor';
	import Palette from '@lucide/svelte/icons/palette';
	import SortAsc from '@lucide/svelte/icons/sort-asc';
	import Trash2 from '@lucide/svelte/icons/trash-2';
	import Volume2 from '@lucide/svelte/icons/volume-2';
	import Waypoints from '@lucide/svelte/icons/waypoints';
	import { toast } from 'svelte-sonner';

	import CookiesPanel from '$lib/components/CookiesPanel.svelte';
	import { Button } from '$lib/components/ui/button';
	import { Label } from '$lib/components/ui/label';
	import * as Sheet from '$lib/components/ui/sheet';
	import { Switch } from '$lib/components/ui/switch';
	import { i18n } from '$lib/i18n/index.svelte';
	import { appStore } from '$lib/stores/app-state.svelte';

	const { t } = i18n;

	let {
		preferences,
		isPreferencesDialogOpen = $bindable()
	}: { preferences: typeof appStore.preferences; isPreferencesDialogOpen?: boolean } = $props();

	const sections = [
		{
			titleKey: 'prefs.section.interface',
			icon: Monitor,
			color: 'text-blue-600',
			settings: [
				{
					id: 'show-thumbnails',
					labelKey: 'prefs.showThumbnails.label',
					key: 'showVideoThumbnail',
					descKey: 'prefs.showThumbnails.desc'
				},
				{
					id: 'animations-enabled',
					labelKey: 'prefs.animations.label',
					key: 'enableAnimations',
					descKey: 'prefs.animations.desc'
				},
				{
					id: 'compact-mode',
					labelKey: 'prefs.compact.label',
					key: 'enableCompact',
					descKey: 'prefs.compact.desc'
				}
			]
		},
		{
			titleKey: 'prefs.section.playback',
			icon: Volume2,
			color: 'text-green-600',
			settings: [
				{
					id: 'mute-by-default',
					labelKey: 'prefs.mute.label',
					key: 'enableVideoMute',
					descKey: 'prefs.mute.desc'
				},
				{
					id: 'preload-metadata',
					labelKey: 'prefs.preload.label',
					key: 'enableVideoPreloadMetadata',
					defaultTrue: true,
					descKey: 'prefs.preload.desc'
				},
				{
					id: 'show-video-only',
					labelKey: 'prefs.videoOnly.label',
					key: 'showVideoOnlyFormats',
					descKey: 'prefs.videoOnly.desc'
				}
			]
		},
		{
			titleKey: 'prefs.section.proxy',
			icon: Waypoints,
			color: 'text-cyan-600',
			settings: [
				{
					id: 'use-proxy',
					labelKey: 'prefs.useProxy.label',
					key: 'enableProxyForVideoExtract',
					defaultTrue: true,
					descKey: 'prefs.useProxy.desc'
				},
				{
					id: 'show-hls-download-button',
					labelKey: 'prefs.hlsDownload.label',
					key: 'showHlsTypeDownloadButton',
					descKey: 'prefs.hlsDownload.desc'
				}
			]
		}
	] as const;

	function resetToDefaults() {
		appStore.updatePreferences({
			theme: 'system',
			layoutList: 'grid',
			videoSortField: 'quality',
			videoSortOrder: 'desc',
			showVideoThumbnail: true,
			enableAnimations: true,
			enableCompact: false,
			enableVideoMute: false,
			enableVideoPreloadMetadata: false,
			enableProxyForVideoExtract: true,
			showHlsTypeDownloadButton: false,
			showVideoOnlyFormats: false
		});
		toast.success(t('toast.prefsReset'));
	}

	function clearAllData() {
		appStore.reset();
		toast.success(t('toast.dataCleared'));
	}
</script>

<Sheet.Root bind:open={isPreferencesDialogOpen}>
	<Sheet.Content
		side="right"
		class="bg-background z-999999! w-full gap-0 overflow-y-auto p-4 sm:max-w-lg sm:p-6"
	>
		<Sheet.Header class="px-0 text-start">
			<Sheet.Title class="ds-gradient-text text-xl font-bold sm:text-2xl">
				{t('prefs.title')}
			</Sheet.Title>
			<Sheet.Description class="text-muted-foreground text-sm">
				{t('prefs.subtitle')}
			</Sheet.Description>
		</Sheet.Header>

		<div class="space-y-4 pb-4 sm:space-y-8 sm:pb-6">
			{#each sections as section (section.titleKey)}
				<section class="rounded-lg border bg-white dark:border-zinc-700 dark:bg-zinc-800/50">
					<!-- Section Content -->
					<div class="p-3 sm:p-4">
						<div class="grid grid-cols-1 gap-3 sm:grid-cols-2 sm:gap-4">
							{#each section.settings as setting (setting.id)}
								<div
									class="flex items-start justify-between rounded-lg bg-zinc-50 p-3 transition-colors hover:bg-zinc-100 dark:bg-zinc-800/50 dark:hover:bg-zinc-800"
								>
									<div class="flex-1 pe-3">
										<div class="flex items-center gap-2">
											<Label for={setting.id} class="cursor-pointer text-sm font-medium">
												{t(setting.labelKey)}
											</Label>
											<button
												type="button"
												title={t(setting.descKey)}
												class="text-zinc-400 transition-colors hover:text-zinc-600 dark:text-zinc-500 dark:hover:text-zinc-300"
											>
												<Info class="h-3 w-3" />
											</button>
										</div>
										<p class="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
											{t(setting.descKey)}
										</p>
									</div>
									<Switch
										id={setting.id}
										checked={'defaultTrue' in setting && setting.defaultTrue
											? preferences[setting.key as keyof typeof preferences] !== false
											: preferences[setting.key as keyof typeof preferences] === true}
										onCheckedChange={(checked) =>
											appStore.updatePreferences({ [setting.key]: checked })}
									/>
								</div>
							{/each}
						</div>
					</div>
				</section>
			{/each}

			<!-- Cookies / sign-in -->
			<CookiesPanel />

			<!-- View Mode Section -->
			<section class="rounded-lg border bg-white dark:border-zinc-700 dark:bg-zinc-800/50">
				<div class="border-b p-3 dark:border-zinc-700">
					<h4 class="flex items-center gap-2 text-base font-semibold">
						<LayoutList class="h-4 w-4 text-purple-600" />
						{t('prefs.viewMode')}
					</h4>
				</div>
				<div class="p-3 sm:p-4">
					<div class="flex flex-col gap-2 sm:flex-row">
						<Button
							variant={preferences.layoutList === 'grid' ? 'default' : 'outline'}
							size="sm"
							onclick={() => appStore.updatePreferences({ layoutList: 'grid' })}
							class="h-11 py-1.5 flex-1 cursor-pointer justify-center px-4 sm:h-10 sm:flex-none sm:justify-start"
						>
							<Grid3X3 class="me-2 h-4 w-4" />
							{t('prefs.gridView')}
						</Button>
						<Button
							variant={preferences.layoutList === 'list' ? 'default' : 'outline'}
							size="sm"
							onclick={() => appStore.updatePreferences({ layoutList: 'list' })}
							class="h-11 py-1.5 flex-1 cursor-pointer justify-center px-4 sm:h-10 sm:flex-none sm:justify-start"
						>
							<LayoutList class="me-2 h-4 w-4" />
							{t('prefs.listView')}
						</Button>
					</div>
				</div>
			</section>
			<!-- Sorting Options Section -->
			<section class="rounded-lg border bg-white dark:border-zinc-700 dark:bg-zinc-800/50">
				<div class="border-b p-3 dark:border-zinc-700">
					<h4 class="flex items-center gap-2 text-base font-semibold">
						<SortAsc class="h-4 w-4 text-orange-600" />
						{t('prefs.sorting')}
					</h4>
				</div>
				<div class="p-3 sm:p-4">
					<div class="space-y-4">
						<!-- Sort By -->
						<div class="space-y-2">
							<Label class="text-sm font-medium">{t('prefs.sortBy')}</Label>
							<div class="flex flex-col gap-2 sm:flex-row">
								{#each ['name', 'size', 'quality'] as const as sortOption (sortOption)}
									<Button
										variant={preferences.videoSortField === sortOption ? 'default' : 'outline'}
										size="sm"
										onclick={() =>
											appStore.updatePreferences({
												videoSortField: sortOption
											})}
										class="h-11 py-1.5 flex-1 cursor-pointer justify-center px-4 sm:h-10 sm:flex-none sm:justify-start"
									>
										{t(`prefs.sort.${sortOption}`)}
									</Button>
								{/each}
							</div>
						</div>

						<!-- Sort Order -->
						<div class="space-y-2">
							<Label class="text-sm font-medium">{t('prefs.sortOrder')}</Label>
							<div class="flex flex-col gap-2 sm:flex-row">
								<Button
									variant={preferences.videoSortOrder === 'asc' ? 'default' : 'outline'}
									size="sm"
									onclick={() => appStore.updatePreferences({ videoSortOrder: 'asc' })}
									class="h-11 py-1.5 flex-1 cursor-pointer justify-center px-4 sm:h-10 sm:flex-none sm:justify-start"
								>
									{t('prefs.ascending')}
								</Button>
								<Button
									variant={preferences.videoSortOrder === 'desc' ? 'default' : 'outline'}
									size="sm"
									onclick={() => appStore.updatePreferences({ videoSortOrder: 'desc' })}
									class="h-11 py-1.5 flex-1 cursor-pointer justify-center px-4 sm:h-10 sm:flex-none sm:justify-start"
								>
									{t('prefs.descending')}
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
						{t('prefs.themeSection')}
					</h4>
				</div>
				<div class="p-3 sm:p-4">
					<div class="space-y-2">
						<Label class="text-sm font-medium">{t('prefs.themeLabel')}</Label>
						<div class="flex flex-col gap-2 sm:flex-row">
							{#each ['light', 'dark', 'system'] as const as theme (theme)}
								<Button
									variant={preferences.theme === theme ? 'default' : 'outline'}
									size="sm"
									onclick={() => appStore.updatePreferences({ theme })}
									class="h-11 py-1.5 flex-1 cursor-pointer justify-center px-4 sm:h-10 sm:flex-none sm:justify-start"
								>
									{t(`prefs.theme.${theme}`)}
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
						{t('prefs.storedData')}
					</h4>
				</div>
				<div class="p-3 sm:p-4">
					<div class="space-y-4">
						<!-- Stats Card -->
						<div class="grid grid-cols-1 gap-3 sm:gap-4">
							<div class="bg-muted/60 rounded-xl border p-3 text-center sm:p-4">
								<div class="text-primary text-xl font-bold sm:text-3xl">
									{appStore.getStats().extracted}
								</div>
								<div class="text-muted-foreground text-xs font-medium sm:text-sm">
									{t('prefs.extractedVideos')}
								</div>
							</div>
						</div>

						<Button
							variant="outline"
							size="sm"
							onclick={() => {
								appStore.reset();
								toast.success(t('toast.dataCleared'));
							}}
							class="w-full h-11 sm:h-10 py-1.5 cursor-pointer px-4 transition-colors hover:border-red-300 hover:bg-red-50 hover:text-red-700 dark:hover:border-red-700 dark:hover:bg-red-900/10 dark:hover:text-red-400"
						>
							<Trash2 class="me-2 h-4 w-4" />
							{t('prefs.clearData')}
						</Button>
					</div>
				</div>
			</section>

			<!-- Reset Section -->
			<section class="rounded-lg border bg-white dark:border-zinc-700 dark:bg-zinc-800/50">
				<div class="border-b p-3 dark:border-zinc-700">
					<h4 class="flex items-center gap-2 text-base font-semibold">
						<AlertCircle class="h-4 w-4 text-red-600" />
						{t('prefs.resetSection')}
					</h4>
				</div>
				<div class="p-3 sm:p-4">
					<div class="flex flex-col gap-3 sm:flex-row sm:gap-4">
						<Button variant="outline" onclick={resetToDefaults} class="flex-1 cursor-pointer">
							{t('prefs.resetDefaults')}
						</Button>
						<Button variant="destructive" onclick={clearAllData} class="flex-1 cursor-pointer">
							<Trash2 class="me-2 h-4 w-4" />
							{t('prefs.clearData')}
						</Button>
					</div>
				</div>
			</section>
		</div>
	</Sheet.Content>
</Sheet.Root>
