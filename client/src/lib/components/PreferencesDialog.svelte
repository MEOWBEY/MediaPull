<script lang="ts">
	import AlertCircle from '@lucide/svelte/icons/alert-circle';
	import Captions from '@lucide/svelte/icons/captions';
	import Download from '@lucide/svelte/icons/download';
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
	import Trash2 from '@lucide/svelte/icons/trash-2';
	import Volume2 from '@lucide/svelte/icons/volume-2';
	import Waypoints from '@lucide/svelte/icons/waypoints';
	import { toast } from 'svelte-sonner';

	import CookiesPanel from '$lib/components/CookiesPanel.svelte';
	import { Button } from '$lib/components/ui/button';
	import { Label } from '$lib/components/ui/label';
	import * as Sheet from '$lib/components/ui/sheet';
	import { Switch } from '$lib/components/ui/switch';
	import { formatBytesToMB } from '$lib/format';
	import { i18n, LOCALES } from '$lib/i18n/index.svelte';
	import type { MessageKey } from '$lib/i18n/index.svelte';
	import { appStore } from '$lib/stores/app-state.svelte';
	import { localFiles } from '$lib/stores/local-library.svelte';
	import { ui } from '$lib/stores/ui.svelte';
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
	// Two separate armed flags: clearing the whole app (library + preferences +
	// local files) is far more destructive than clearing just local files.
	let confirmClear = $state(false);
	let confirmClearLocal = $state(false);

	$effect(() => {
		if (!isPreferencesDialogOpen) {
			confirmClear = false;
			confirmClearLocal = false;
		}
	});

	// Deep-link: when a caller opened the dialog targeting a specific tab (error
	// banner → cookies, video-only note → playback), switch to it once, then
	// clear the request so a manual tab change afterward isn't overridden.
	$effect(() => {
		if (isPreferencesDialogOpen && ui.preferencesTab) {
			tab = ui.preferencesTab;
			ui.preferencesTab = null;
		}
	});

	type SettingItem = {
		id: string;
		labelKey: MessageKey;
		key: string;
		descKey: MessageKey;
		defaultTrue?: boolean;
	};

	// Toggle groups, assigned to tabs. General holds interface prefs; Player
	// holds playback + proxy toggles. Keys are unchanged -- this only groups
	// existing preferences, it does not invent new ones.
	const interfaceSettings: SettingItem[] = [
		{
			id: 'show-thumbnails',
			labelKey: 'prefs.showThumbnails.label',
			key: 'showVideoThumbnail',
			descKey: 'prefs.showThumbnails.desc'
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

	// Result-list export buttons (Links .txt / Playlist .m3u) -- off by default,
	// lives in the Downloads tab since it's about what the result group shows.
	const exportSettings: SettingItem[] = [
		{
			id: 'show-export-buttons',
			labelKey: 'prefs.showExports.label',
			key: 'showExportButtons',
			descKey: 'prefs.showExports.desc'
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
			layoutList: 'row',
			showVideoThumbnail: true,
			enableVideoMute: false,
			enableVideoPreloadMetadata: false,
			enableProxyForVideoExtract: true,
			showHlsTypeDownloadButton: true,
			showExportButtons: false,
			showVideoOnlyFormats: false,
			subtitlePanelMinWords: 0
		});
		toast.success(t('toast.prefsReset'));
	}

	function clearAllData() {
		appStore.reset();
		localFiles.clear();
		confirmClear = false;
		toast.success(t('toast.dataCleared'));
	}

	function clearLocalFiles() {
		localFiles.clear();
		confirmClearLocal = false;
		toast.success(t('toast.localFilesCleared'));
	}
</script>

<!-- `color` must be a token class (text-signal / text-destructive / text-warning):
     the design system has one accent, and raw Tailwind palette colors would not
     recolor with a token reskin. -->
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
						<span title={t(setting.descKey)} class="text-muted-foreground/70">
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
		class="bg-background z-999999! flex w-full flex-col gap-0 overflow-hidden p-0 sm:max-w-2xl {desktop.matches
			? ''
			: 'h-[80dvh] rounded-t-2xl'}"
	>
		<Sheet.Header class="px-4 pt-12 text-start sm:px-6">
			<Sheet.Title class="font-heading text-xl font-bold sm:text-2xl">
				{t('prefs.title')}
			</Sheet.Title>
		</Sheet.Header>

		<!-- Tab bar: mono underline style, matching the video player's format tabs.
		     Each tab's bottom edge overlaps the container border-b (-mb-px); the
		     active tab's 2px bar sits flush at that same line (bottom-0), so it
		     reads as the border thickening under the active tab rather than a
		     separate floating underline. -->
		<div class="border-border/70 mt-3 border-b px-4 sm:px-6" role="tablist">
			<div class="flex w-full items-stretch gap-5">
				{#each tabs as tabItem (tabItem.id)}
					<button
						type="button"
						role="tab"
						aria-selected={tab === tabItem.id}
						onclick={() => (tab = tabItem.id)}
						class="relative -mb-px cursor-pointer pt-1 pb-2.5 font-mono text-xs font-semibold tracking-wide uppercase transition-colors sm:text-sm {tab ===
						tabItem.id
							? 'text-signal'
							: 'text-muted-foreground hover:text-foreground'}"
					>
						{t(tabItem.labelKey)}
						{#if tab === tabItem.id}
							<span class="bg-signal absolute inset-x-0 bottom-0 h-0.5"></span>
						{/if}
					</button>
				{/each}
			</div>
		</div>

		<div class="flex-1 space-y-4 overflow-y-auto px-4 pt-2 pb-8 sm:space-y-6 sm:px-6 sm:pb-10">
			{#if tab === 'general'}
				{#snippet interfaceBody()}
					{@render toggleGroup(interfaceSettings)}
				{/snippet}
				{@render sectionCard('prefs.section.interface', Monitor, 'text-signal', interfaceBody)}

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
									class="h-12 py-2 flex-1 cursor-pointer justify-center px-4 sm:h-10 sm:py-1.5 sm:flex-none sm:justify-start"
								>
									{t(`prefs.contentType.${mode}`)}
								</Button>
							{/each}
						</div>
					</div>
				{/snippet}
				{@render sectionCard('prefs.contentTypeSection', Image, 'text-signal', contentTypeBody)}

				{#snippet themeBody()}
					<div class="space-y-2">
						<Label class="text-sm font-medium">{t('prefs.themeLabel')}</Label>
						<div class="flex flex-col gap-2 sm:flex-row">
							{#each ['light', 'dark', 'system'] as const as theme (theme)}
								<Button
									variant={preferences.theme === theme ? 'default' : 'outline'}
									size="sm"
									onclick={() => appStore.updatePreferences({ theme })}
									class="h-12 py-2 flex-1 cursor-pointer justify-center px-4 sm:h-10 sm:py-1.5 sm:flex-none sm:justify-start"
								>
									{t(`prefs.theme.${theme}`)}
								</Button>
							{/each}
						</div>
					</div>
				{/snippet}
				{@render sectionCard('prefs.themeSection', Palette, 'text-signal', themeBody)}

				{#snippet languageBody()}
					<div class="space-y-2">
						<Label class="text-sm font-medium">{t('prefs.languageLabel')}</Label>
						<div class="flex flex-col gap-2 sm:flex-row">
							{#each LOCALES as loc (loc.code)}
								<Button
									variant={i18n.locale === loc.code ? 'default' : 'outline'}
									size="sm"
									onclick={() => i18n.setLocale(loc.code)}
									class="h-12 py-2 flex-1 cursor-pointer justify-center px-4 sm:h-10 sm:py-1.5 sm:flex-none sm:justify-start"
								>
									{loc.label}
								</Button>
							{/each}
						</div>
					</div>
				{/snippet}
				{@render sectionCard('prefs.languageSection', Languages, 'text-signal', languageBody)}
			{:else if tab === 'library'}
				{#snippet viewModeBody()}
					<div class="flex flex-col gap-2 sm:flex-row">
						<Button
							variant={preferences.layoutList === 'grid' ? 'default' : 'outline'}
							size="sm"
							onclick={() => appStore.updatePreferences({ layoutList: 'grid' })}
							class="h-12 py-2 flex-1 cursor-pointer justify-center px-4 sm:h-10 sm:py-1.5 sm:flex-none sm:justify-start"
						>
							<Grid3X3 class="me-2 h-4 w-4" />
							{t('prefs.gridView')}
						</Button>
						<Button
							variant={preferences.layoutList === 'row' ? 'default' : 'outline'}
							size="sm"
							onclick={() => appStore.updatePreferences({ layoutList: 'row' })}
							class="h-12 py-2 flex-1 cursor-pointer justify-center px-4 sm:h-10 sm:py-1.5 sm:flex-none sm:justify-start"
						>
							<LayoutList class="me-2 h-4 w-4" />
							{t('prefs.rowView')}
						</Button>
					</div>
				{/snippet}
				{@render sectionCard('prefs.viewMode', LayoutList, 'text-signal', viewModeBody)}

				{#snippet exportsBody()}
					{@render toggleGroup(exportSettings)}
				{/snippet}
				{@render sectionCard('prefs.section.exports', Download, 'text-signal', exportsBody)}

				{#snippet storedBody()}
					<div class="space-y-4">
						<div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
							<div class="bg-muted/60 rounded-xl border p-3 text-center sm:p-4">
								<div class="text-primary text-xl font-bold sm:text-3xl">
									{appStore.getStats().extracted}
								</div>
								<div class="text-muted-foreground text-xs font-medium sm:text-sm">
									{t('prefs.extractedVideos')}
								</div>
							</div>

							<div class="bg-muted/60 rounded-xl border p-3 text-center sm:p-4">
								<div class="text-primary text-xl font-bold sm:text-3xl">
									{localFiles.entries.length}
								</div>
								<div class="text-muted-foreground text-xs font-medium sm:text-sm">
									{t('prefs.localFiles')}
								</div>
								<div class="text-muted-foreground/70 mt-1 text-xs" title={t('prefs.storedSize')}>
									{localFiles.usedBytes > 0 ? formatBytesToMB(localFiles.usedBytes) : '0 MB'}
								</div>
							</div>
						</div>

						{#if confirmClearLocal}
							<div class="border-destructive/40 bg-destructive/5 space-y-3 rounded-xl border p-3">
								<p class="text-sm">{t('prefs.confirmClearLocal')}</p>
								<div class="flex flex-col gap-2 sm:flex-row">
									<Button
										variant="destructive"
										size="sm"
										onclick={clearLocalFiles}
										class="flex-1 cursor-pointer"
									>
										<Trash2 class="me-2 h-4 w-4" />
										{t('prefs.confirmClearYes')}
									</Button>
									<Button
										variant="outline"
										size="sm"
										onclick={() => (confirmClearLocal = false)}
										class="flex-1 cursor-pointer"
									>
										{t('prefs.confirmClearNo')}
									</Button>
								</div>
							</div>
						{:else if !confirmClear}
							<Button
								variant="outline"
								size="sm"
								disabled={localFiles.entries.length === 0}
								onclick={() => (confirmClearLocal = true)}
								class="hover:bg-destructive/10 hover:text-destructive hover:border-destructive/40 h-12 w-full cursor-pointer px-4 py-2 transition-colors disabled:cursor-not-allowed disabled:opacity-50 sm:h-10 sm:py-1.5"
							>
								<HardDrive class="me-2 h-4 w-4" />
								{t('prefs.clearLocalFiles')}
							</Button>
						{/if}

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
								class="hover:bg-destructive/10 hover:text-destructive hover:border-destructive/40 h-12 w-full cursor-pointer px-4 py-2 transition-colors sm:h-10 sm:py-1.5"
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
				{@render sectionCard('prefs.section.playback', Volume2, 'text-signal', playbackBody)}

				{#snippet proxyBody()}
					{@render toggleGroup(proxySettings)}
				{/snippet}
				{@render sectionCard('prefs.section.proxy', Waypoints, 'text-signal', proxyBody)}

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
							<span
								class="text-muted-foreground flex min-w-14 items-center justify-center px-2 font-mono text-sm font-semibold tabular-nums"
							>
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
				{@render sectionCard('prefs.subtitlePanelSection', Captions, 'text-signal', minWordsBody)}
			{:else if tab === 'cookies'}
				<CookiesPanel />
			{/if}
		</div>
	</Sheet.Content>
</Sheet.Root>
