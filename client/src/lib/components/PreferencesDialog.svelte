<script lang="ts">
	import AlertCircle from '@lucide/svelte/icons/alert-circle';
	import Captions from '@lucide/svelte/icons/captions';
	import Grid3X3 from '@lucide/svelte/icons/grid-3x3';
	import HardDrive from '@lucide/svelte/icons/hard-drive';
	import Image from '@lucide/svelte/icons/image';
	import Info from '@lucide/svelte/icons/info';
	import Languages from '@lucide/svelte/icons/languages';
	import LayoutList from '@lucide/svelte/icons/layout-list';
	import Minus from '@lucide/svelte/icons/minus';
	import Monitor from '@lucide/svelte/icons/monitor';
	import Palette from '@lucide/svelte/icons/palette';
	import Plus from '@lucide/svelte/icons/plus';
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
	import { i18n, LOCALES } from '$lib/i18n/index.svelte';
	import { appStore } from '$lib/stores/app-state.svelte';
	import { MediaQuery } from '$lib/viewport.svelte';

	const { t } = i18n;

	let {
		preferences,
		isPreferencesDialogOpen = $bindable()
	}: { preferences: typeof appStore.preferences; isPreferencesDialogOpen?: boolean } = $props();

	// Side sheet on desktop, bottom sheet on mobile -- same pattern as SubtitlePanel.
	const desktop = new MediaQuery('(min-width: 640px)');

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
		},
		{
			titleKey: 'prefs.section.captions',
			icon: Captions,
			color: 'text-violet-600',
			settings: [
				{
					id: 'auto-open-subtitle-panel',
					labelKey: 'prefs.autoOpenSubs.label',
					key: 'autoOpenSubtitlePanel',
					descKey: 'prefs.autoOpenSubs.desc'
				}
			]
		}
	] as const;

	// Clamp the subtitle-panel minimum-word filter to a sane range. 0 disables
	// the filter (every line shows); the ceiling just stops the stepper running
	// away -- most caption lines are only a handful of words.
	const MIN_WORDS_MAX = 12;

	function setMinWords(next: number) {
		appStore.updatePreferences({
			subtitlePanelMinWords: Math.max(0, Math.min(MIN_WORDS_MAX, next))
		});
	}

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
			showHlsTypeDownloadButton: true,
			showVideoOnlyFormats: false,
			autoOpenSubtitlePanel: false,
			subtitlePanelMinWords: 0
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
		side={desktop.matches ? 'right' : 'bottom'}
		closeLabel={t('common.close')}
		hideClose
		class="bg-background z-999999! w-full gap-0 overflow-y-auto p-4 sm:max-w-lg sm:p-6 {desktop.matches
			? ''
			: 'h-[65vh] rounded-t-3xl'}"
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
				<section class="bg-card rounded-lg border">
					<!-- Section Content -->
					<div class="p-3 sm:p-4">
						<div class="grid grid-cols-1 gap-3 sm:grid-cols-2 sm:gap-4">
							{#each section.settings as setting (setting.id)}
								<div
									class="bg-muted/60 hover:bg-muted flex items-start justify-between rounded-lg p-3 transition-colors"
								>
									<div class="flex-1 pe-3">
										<div class="flex items-center gap-2">
											<Label for={setting.id} class="cursor-pointer text-sm font-medium">
												{t(setting.labelKey)}
											</Label>
											<button
												type="button"
												title={t(setting.descKey)}
												aria-label={t(setting.descKey)}
												class="text-muted-foreground hover:text-foreground transition-colors"
											>
												<Info class="h-3 w-3" />
											</button>
										</div>
										<p class="mt-1 text-xs text-muted-foreground">
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

			<!-- Subtitle panel: minimum words per line. A stepper (not a Switch)
			     since it's a numeric threshold; 0 means "show every line". Only
			     filters the panel list -- the video itself keeps all captions. -->
			<section class="bg-card rounded-lg border">
				<div class="border-border/60 border-b p-3">
					<h4 class="flex items-center gap-2 text-base font-semibold">
						<Captions class="h-4 w-4 text-violet-600" />
						{t('prefs.subtitlePanelSection')}
					</h4>
				</div>
				<div class="p-3 sm:p-4">
					<div class="bg-muted/60 flex items-start justify-between gap-3 rounded-lg p-3">
						<div class="flex-1 pe-1">
							<Label class="text-sm font-medium">{t('prefs.minWords.label')}</Label>
							<p class="text-muted-foreground mt-1 text-xs">{t('prefs.minWords.desc')}</p>
						</div>
						<div class="flex shrink-0 items-center gap-2">
							<Button
								variant="outline"
								size="icon"
								class="h-9 w-9"
								disabled={preferences.subtitlePanelMinWords <= 0}
								onclick={() => setMinWords(preferences.subtitlePanelMinWords - 1)}
								aria-label={t('prefs.minWords.decrease')}
							>
								<Minus class="h-4 w-4" />
							</Button>
							<span class="w-10 text-center text-sm font-semibold tabular-nums">
								{preferences.subtitlePanelMinWords === 0
									? t('prefs.minWords.off')
									: preferences.subtitlePanelMinWords}
							</span>
							<Button
								variant="outline"
								size="icon"
								class="h-9 w-9"
								disabled={preferences.subtitlePanelMinWords >= MIN_WORDS_MAX}
								onclick={() => setMinWords(preferences.subtitlePanelMinWords + 1)}
								aria-label={t('prefs.minWords.increase')}
							>
								<Plus class="h-4 w-4" />
							</Button>
						</div>
					</div>
				</div>
			</section>

			<!-- Cookies / sign-in -->
			<CookiesPanel />

			<!-- View Mode Section -->
			<section class="bg-card rounded-lg border">
				<div class="border-border/60 border-b p-3">
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
			<section class="bg-card rounded-lg border">
				<div class="border-border/60 border-b p-3">
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

			<!-- Content Type Section -->
			<section class="bg-card rounded-lg border">
				<div class="border-border/60 border-b p-3">
					<h4 class="flex items-center gap-2 text-base font-semibold">
						<Image class="h-4 w-4 text-teal-600" />
						{t('prefs.contentTypeSection')}
					</h4>
				</div>
				<div class="p-3 sm:p-4">
					<div class="space-y-2">
						<Label class="text-sm font-medium">{t('prefs.contentTypeLabel')}</Label>
						<p class="text-muted-foreground text-xs">{t('prefs.contentTypeDesc')}</p>
						<div class="flex flex-col gap-2 sm:flex-row">
							{#each ['auto', 'video', 'gallery'] as const as mode (mode)}
								<Button
									variant={preferences.contentTypeMode === mode ? 'default' : 'outline'}
									size="sm"
									onclick={() => appStore.updatePreferences({ contentTypeMode: mode })}
									class="h-11 py-1.5 flex-1 cursor-pointer justify-center px-4 sm:h-10 sm:flex-none sm:justify-start"
								>
									{t(`prefs.contentType.${mode}`)}
								</Button>
							{/each}
						</div>
					</div>
				</div>
			</section>

			<!-- Theme Selection -->
			<section class="bg-card rounded-lg border">
				<div class="border-border/60 border-b p-3">
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

			<!-- Language Section -->
			<section class="bg-card rounded-lg border">
				<div class="border-border/60 border-b p-3">
					<h4 class="flex items-center gap-2 text-base font-semibold">
						<Languages class="h-4 w-4 text-indigo-600" />
						{t('prefs.languageSection')}
					</h4>
				</div>
				<div class="p-3 sm:p-4">
					<div class="space-y-2">
						<Label class="text-sm font-medium">{t('prefs.languageLabel')}</Label>
						<div class="flex flex-col gap-2 sm:flex-row">
							{#each LOCALES as loc (loc.code)}
								<Button
									variant={i18n.locale === loc.code ? 'default' : 'outline'}
									size="sm"
									onclick={() => i18n.setLocale(loc.code)}
									class="h-11 py-1.5 flex-1 cursor-pointer justify-center px-4 sm:h-10 sm:flex-none sm:justify-start"
								>
									{loc.label}
								</Button>
							{/each}
						</div>
					</div>
				</div>
			</section>

			<!-- Cache & Store Section -->
			<section class="bg-card rounded-lg border">
				<div class="border-border/60 border-b p-3">
					<h4 class="flex items-center gap-2 text-base font-semibold">
						<HardDrive class="text-destructive h-4 w-4" />
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
							class="hover:bg-destructive/10 hover:text-destructive hover:border-destructive/40 h-11 w-full cursor-pointer px-4 py-1.5 transition-colors sm:h-10"
						>
							<Trash2 class="me-2 h-4 w-4" />
							{t('prefs.clearData')}
						</Button>
					</div>
				</div>
			</section>

			<!-- Reset Section -->
			<section class="bg-card rounded-lg border">
				<div class="border-border/60 border-b p-3">
					<h4 class="flex items-center gap-2 text-base font-semibold">
						<AlertCircle class="text-destructive h-4 w-4" />
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
