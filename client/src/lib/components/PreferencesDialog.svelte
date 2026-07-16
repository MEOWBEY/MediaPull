<script lang="ts">
	import AlertCircle from '@lucide/svelte/icons/alert-circle';
	import Captions from '@lucide/svelte/icons/captions';
	import Grid3X3 from '@lucide/svelte/icons/grid-3x3';
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
	import type { MessageKey } from '$lib/i18n/index.svelte';
	import { appStore } from '$lib/stores/app-state.svelte';
	import { MediaQuery } from '$lib/viewport.svelte';

	import type { Component, Snippet } from 'svelte';

	const { t } = i18n;

	let {
		preferences,
		isPreferencesDialogOpen = $bindable()
	}: { preferences: typeof appStore.preferences; isPreferencesDialogOpen?: boolean } = $props();

	// Side sheet on desktop, bottom sheet on mobile -- same pattern as SubtitlePanel.
	const desktop = new MediaQuery('(min-width: 640px)');

	type PrefsTab = 'general' | 'library' | 'playback' | 'cookies';
	let tab = $state<PrefsTab>('general');

	const tabs: Array<{ id: PrefsTab; labelKey: MessageKey }> = [
		{ id: 'general', labelKey: 'prefs.tab.general' },
		{ id: 'library', labelKey: 'prefs.tab.library' },
		{ id: 'playback', labelKey: 'prefs.tab.playback' },
		{ id: 'cookies', labelKey: 'prefs.tab.cookies' }
	];

	// Two-step confirm for the destructive "clear library" action so a stray tap
	// on mobile can't wipe everything. Reset on close so it never re-opens armed.
	let confirmClear = $state(false);

	$effect(() => {
		if (!isPreferencesDialogOpen) {
			confirmClear = false;
		}
	});

	type SettingItem = {
		id: string;
		labelKey: MessageKey;
		key: string;
		descKey: MessageKey;
		defaultTrue?: boolean;
	};

	// Toggle groups, now assigned to tabs. General holds interface prefs;
	// Playback holds playback + proxy + captions toggles. Keys are unchanged --
	// this only regroups existing preferences, it does not invent new ones.
	const interfaceSettings: SettingItem[] = [
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
	];

	const playbackSettings: SettingItem[] = [
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
	];

	// Proxy + HLS are power features -- grouped together under Playback so they
	// don't crowd the first thing a normal user sees.
	const proxySettings: SettingItem[] = [
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
	];

	const captionSettings: SettingItem[] = [
		{
			id: 'auto-open-subtitle-panel',
			labelKey: 'prefs.autoOpenSubs.label',
			key: 'autoOpenSubtitlePanel',
			descKey: 'prefs.autoOpenSubs.desc'
		}
	];

	// Clamp the subtitle-panel minimum-word filter to a sane range. 0 disables
	// the filter (every line shows); the ceiling just stops the stepper running
	// away -- most caption lines are only a handful of words.
	const MIN_WORDS_MAX = 12;

	function setMinWords(next: number) {
		appStore.updatePreferences({
			subtitlePanelMinWords: Math.max(0, Math.min(MIN_WORDS_MAX, next))
		});
	}

	function isOn(setting: SettingItem): boolean {
		return setting.defaultTrue
			? preferences[setting.key as keyof typeof preferences] !== false
			: preferences[setting.key as keyof typeof preferences] === true;
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
		confirmClear = false;
		toast.success(t('toast.dataCleared'));
	}
</script>

{#snippet sectionCard(titleKey: MessageKey, Icon: Component, color: string, body: Snippet)}
	<section class="bg-card rounded-lg border">
		<div class="border-border/60 border-b p-3">
			<h4 class="flex items-center gap-2 text-base font-semibold">
				<Icon class="h-4 w-4 {color}" />
				{t(titleKey)}
			</h4>
		</div>
		<div class="p-3 sm:p-4">
			{@render body()}
		</div>
	</section>
{/snippet}

{#snippet toggleGroup(settings: SettingItem[])}
	<div class="grid grid-cols-1 gap-3 sm:grid-cols-2 sm:gap-4">
		{#each settings as setting (setting.id)}
			<div
				class="bg-muted/60 hover:bg-muted flex items-start justify-between rounded-lg p-3 transition-colors"
			>
				<div class="flex-1 pe-3">
					<div class="flex items-center gap-2">
						<Label for={setting.id} class="cursor-pointer text-sm font-medium">
							{t(setting.labelKey)}
						</Label>
						<span
							title={t(setting.descKey)}
							class="text-muted-foreground/70"
						>
							<Info class="h-3 w-3" />
						</span>
					</div>
					<p class="mt-1 text-xs text-muted-foreground">
						{t(setting.descKey)}
					</p>
				</div>
				<Switch
					id={setting.id}
					checked={isOn(setting)}
					onCheckedChange={(checked) => appStore.updatePreferences({ [setting.key]: checked })}
				/>
			</div>
		{/each}
	</div>
{/snippet}

<Sheet.Root bind:open={isPreferencesDialogOpen}>
	<Sheet.Content
		side={desktop.matches ? 'right' : 'bottom'}
		closeLabel={t('common.close')}
		hideClose
		class="bg-background z-999999! flex w-full flex-col gap-0 overflow-hidden p-0 sm:max-w-lg {desktop.matches
			? ''
			: 'h-[88vh] rounded-t-3xl'}"
	>
		<Sheet.Header class="px-4 pt-4 text-start sm:px-6 sm:pt-6">
			<Sheet.Title class="ds-gradient-text text-xl font-bold sm:text-2xl">
				{t('prefs.title')}
			</Sheet.Title>
			<Sheet.Description class="text-muted-foreground text-sm">
				{t('prefs.subtitle')}
			</Sheet.Description>
		</Sheet.Header>

		<!-- Tab bar: segmented control that scrolls to the right panel. -->
		<div class="border-border/60 border-b px-4 pt-3 sm:px-6" role="tablist">
			<div class="bg-muted/50 flex gap-0.5 rounded-full p-0.5">
				{#each tabs as tabItem (tabItem.id)}
					<button
						type="button"
						role="tab"
						aria-selected={tab === tabItem.id}
						onclick={() => (tab = tabItem.id)}
						class="flex-1 rounded-full px-2 py-2 text-xs font-medium transition-colors sm:text-sm {tab ===
						tabItem.id
							? 'bg-background text-foreground shadow-sm'
							: 'text-muted-foreground hover:text-foreground'}"
					>
						{t(tabItem.labelKey)}
					</button>
				{/each}
			</div>
		</div>

		<div class="flex-1 space-y-4 overflow-y-auto px-4 py-4 sm:space-y-6 sm:px-6">
			{#if tab === 'general'}
				{#snippet interfaceBody()}
					{@render toggleGroup(interfaceSettings)}
				{/snippet}
				{@render sectionCard('prefs.section.interface', Monitor, 'text-blue-600', interfaceBody)}

				{#snippet contentTypeBody()}
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
				{/snippet}
				{@render sectionCard('prefs.contentTypeSection', Image, 'text-teal-600', contentTypeBody)}

				{#snippet themeBody()}
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
				{/snippet}
				{@render sectionCard('prefs.themeSection', Palette, 'text-pink-600', themeBody)}

				{#snippet languageBody()}
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
				{/snippet}
				{@render sectionCard('prefs.languageSection', Languages, 'text-indigo-600', languageBody)}
			{:else if tab === 'library'}
				{#snippet viewModeBody()}
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
				{/snippet}
				{@render sectionCard('prefs.viewMode', LayoutList, 'text-purple-600', viewModeBody)}

				{#snippet sortingBody()}
					<div class="space-y-4">
						<div class="space-y-2">
							<Label class="text-sm font-medium">{t('prefs.sortBy')}</Label>
							<div class="flex flex-col gap-2 sm:flex-row">
								{#each ['name', 'size', 'quality'] as const as sortOption (sortOption)}
									<Button
										variant={preferences.videoSortField === sortOption ? 'default' : 'outline'}
										size="sm"
										onclick={() => appStore.updatePreferences({ videoSortField: sortOption })}
										class="h-11 py-1.5 flex-1 cursor-pointer justify-center px-4 sm:h-10 sm:flex-none sm:justify-start"
									>
										{t(`prefs.sort.${sortOption}`)}
									</Button>
								{/each}
							</div>
						</div>
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
				{/snippet}
				{@render sectionCard('prefs.sorting', SortAsc, 'text-orange-600', sortingBody)}

				{#snippet storedBody()}
					<div class="space-y-4">
						<div class="bg-muted/60 rounded-xl border p-3 text-center sm:p-4">
							<div class="text-primary text-xl font-bold sm:text-3xl">
								{appStore.getStats().extracted}
							</div>
							<div class="text-muted-foreground text-xs font-medium sm:text-sm">
								{t('prefs.extractedVideos')}
							</div>
						</div>

						{#if confirmClear}
							<div class="border-destructive/40 bg-destructive/5 space-y-3 rounded-xl border p-3">
								<p class="text-sm">{t('prefs.confirmClear')}</p>
								<div class="flex flex-col gap-2 sm:flex-row">
									<Button
										variant="destructive"
										size="sm"
										onclick={clearAllData}
										class="flex-1 cursor-pointer"
									>
										<Trash2 class="me-2 h-4 w-4" />
										{t('prefs.confirmClearYes')}
									</Button>
									<Button
										variant="outline"
										size="sm"
										onclick={() => (confirmClear = false)}
										class="flex-1 cursor-pointer"
									>
										{t('prefs.confirmClearNo')}
									</Button>
								</div>
							</div>
						{:else}
							<Button
								variant="outline"
								size="sm"
								onclick={() => (confirmClear = true)}
								class="hover:bg-destructive/10 hover:text-destructive hover:border-destructive/40 h-11 w-full cursor-pointer px-4 py-1.5 transition-colors sm:h-10"
							>
								<Trash2 class="me-2 h-4 w-4" />
								{t('prefs.clearData')}
							</Button>
						{/if}
					</div>
				{/snippet}
				{@render sectionCard('prefs.storedData', AlertCircle, 'text-destructive', storedBody)}

				{#snippet resetBody()}
					<Button variant="outline" onclick={resetToDefaults} class="w-full cursor-pointer">
						{t('prefs.resetDefaults')}
					</Button>
				{/snippet}
				{@render sectionCard('prefs.resetSection', AlertCircle, 'text-destructive', resetBody)}
			{:else if tab === 'playback'}
				{#snippet playbackBody()}
					{@render toggleGroup(playbackSettings)}
				{/snippet}
				{@render sectionCard('prefs.section.playback', Volume2, 'text-green-600', playbackBody)}

				{#snippet proxyBody()}
					{@render toggleGroup(proxySettings)}
				{/snippet}
				{@render sectionCard('prefs.section.proxy', Waypoints, 'text-cyan-600', proxyBody)}

				{#snippet captionsBody()}
					{@render toggleGroup(captionSettings)}
				{/snippet}
				{@render sectionCard('prefs.section.captions', Captions, 'text-violet-600', captionsBody)}

				{#snippet minWordsBody()}
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
				{/snippet}
				{@render sectionCard('prefs.subtitlePanelSection', Captions, 'text-violet-600', minWordsBody)}
			{:else if tab === 'cookies'}
				<CookiesPanel />
			{/if}
		</div>
	</Sheet.Content>
</Sheet.Root>
