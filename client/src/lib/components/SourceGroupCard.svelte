<script lang="ts">
	import Copy from '@lucide/svelte/icons/copy';
	import FileText from '@lucide/svelte/icons/file-text';
	import Link from '@lucide/svelte/icons/link';
	import ListMusic from '@lucide/svelte/icons/list-music';
	import RefreshCw from '@lucide/svelte/icons/refresh-cw';
	import Trash2 from '@lucide/svelte/icons/trash-2';

	import { Button } from '$lib/components/ui/button';
	import { i18n } from '$lib/i18n/index.svelte';

	import type { Snippet } from 'svelte';

	const { t } = i18n;

	// Shared bordered group-card shell + header toolbar for both video and
	// gallery result lists -- extracted so the two don't duplicate this chrome.
	// `onExportM3u` is optional: galleries have no playlist-export use case, so
	// omitting it drops that toolbar button entirely. The export buttons only
	// render when `showExports` is on (a preference) -- most users just want the
	// source URL + copy + refresh/remove.
	let {
		sourceUrl,
		itemCount,
		onCopyUrl,
		onExportTxt,
		onExportM3u,
		showExports = false,
		onRefresh,
		refreshing = false,
		onRemove,
		children
	}: {
		sourceUrl: string;
		itemCount: number;
		onCopyUrl?: () => void;
		onExportTxt: () => void;
		onExportM3u?: () => void;
		showExports?: boolean;
		onRefresh: () => void;
		refreshing?: boolean;
		onRemove: () => void;
		children: Snippet;
	} = $props();
</script>

<div
	class="border-border/60 bg-card/60 shadow-soft overflow-hidden rounded-2xl border py-3.5 sm:p-4"
>
	<!-- Group label: origin link + group-wide actions. -->
	<div
		class="border-border/40 mb-3 flex flex-wrap items-center gap-2 border-b px-3.5 pb-2.5 sm:px-0"
	>
		<Link class="text-muted-foreground h-3.5 w-3.5 shrink-0" />
		<div class="flex min-w-0 flex-1 items-center gap-2">
			{#if sourceUrl}
				<!-- External origin page, not in-app navigation, so resolve() doesn't apply. -->
				<!-- eslint-disable svelte/no-navigation-without-resolve -->
				<a
					href={sourceUrl}
					target="_blank"
					rel="noreferrer noopener"
					title={sourceUrl}
					class="text-muted-foreground hover:text-foreground min-w-0 truncate text-start text-xs font-medium underline-offset-2 hover:underline"
				>
					<bdi>{sourceUrl}</bdi>
				</a>
				<!-- eslint-enable svelte/no-navigation-without-resolve -->
			{:else}
				<span class="text-muted-foreground min-w-0 truncate text-xs"
					>{t('extract.sourceUnknown')}</span
				>
			{/if}
			{#if itemCount > 1}
				<span
					class="bg-muted text-muted-foreground shrink-0 rounded-full px-1.5 py-0.5 text-[0.65rem] font-semibold"
				>
					{itemCount}
				</span>
			{/if}
		</div>
		<div class="ms-auto flex shrink-0 items-center gap-0.5">
			{#if onCopyUrl}
				<Button
					variant="ghost"
					size="icon"
					onclick={onCopyUrl}
					class="text-muted-foreground hover:text-foreground h-7 w-7 rounded-full"
					title={t('extract.copyOriginalUrl')}
					aria-label={t('extract.copyOriginalUrl')}
				>
					<Copy class="h-3.5 w-3.5" />
				</Button>
			{/if}
			{#if showExports}
				<Button
					variant="ghost"
					size="icon"
					onclick={onExportTxt}
					class="text-muted-foreground hover:text-foreground h-7 w-7 rounded-full"
					title={t('extract.exportTxt')}
					aria-label={t('extract.exportTxt')}
				>
					<FileText class="h-3.5 w-3.5" />
				</Button>
				{#if onExportM3u}
					<Button
						variant="ghost"
						size="icon"
						onclick={onExportM3u}
						class="text-muted-foreground hover:text-foreground h-7 w-7 rounded-full"
						title={t('extract.exportM3u')}
						aria-label={t('extract.exportM3u')}
					>
						<ListMusic class="h-3.5 w-3.5" />
					</Button>
				{/if}
			{/if}
			<Button
				variant="ghost"
				size="icon"
				onclick={onRefresh}
				disabled={refreshing}
				class="text-muted-foreground hover:text-foreground h-7 w-7 rounded-full"
				title={t('extract.refreshGroup')}
				aria-label={t('extract.refreshGroup')}
			>
				<RefreshCw class="h-3.5 w-3.5 {refreshing ? 'animate-spin' : ''}" />
			</Button>
			<Button
				variant="ghost"
				size="icon"
				onclick={onRemove}
				class="text-muted-foreground hover:text-destructive h-7 w-7 rounded-full"
				title={t('extract.removeGroup')}
				aria-label={t('extract.removeGroup')}
			>
				<Trash2 class="h-3.5 w-3.5" />
			</Button>
		</div>
	</div>

	<!-- Items in this group -- plain content, no per-item card. Caller owns the
	     per-item divider styling (first item vs. rest). -->
	<div class="divide-border/50 divide-y">
		{@render children()}
	</div>
</div>
