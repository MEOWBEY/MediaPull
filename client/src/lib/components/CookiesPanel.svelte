<script lang="ts">
	import Check from '@lucide/svelte/icons/check';
	import ChevronDown from '@lucide/svelte/icons/chevron-down';
	import Cookie from '@lucide/svelte/icons/cookie';
	import Plus from '@lucide/svelte/icons/plus';
	import ShieldAlert from '@lucide/svelte/icons/shield-alert';
	import Trash2 from '@lucide/svelte/icons/trash-2';
	import { toast } from 'svelte-sonner';

	import { Button } from '$lib/components/ui/button';
	import { Label } from '$lib/components/ui/label';
	import { i18n } from '$lib/i18n/index.svelte';
	import { appStore } from '$lib/stores/app-state.svelte';
	import { normalizeDomain } from '$lib/stores/cookies.svelte';

	const { t } = i18n;
	const cookies = appStore.cookies;

	// Famous sites shown by default; any custom domain the user saved is appended.
	const PRESET_DOMAINS = [
		'youtube.com',
		'instagram.com',
		'tiktok.com',
		'facebook.com',
		'x.com',
		'reddit.com',
		'vimeo.com',
		'twitch.tv'
	];

	let showGuide = $state(false);
	let editing = $state<string | null>(null);
	let draft = $state('');
	let customDomain = $state('');
	// Custom domains the user added this session that aren't saved yet — without
	// this they wouldn't appear in `rows`, so their editor never rendered.
	let extraDomains = $state<string[]>([]);

	const rows = $derived.by(() => {
		const saved = cookies.entries().map(([d]) => d);
		const seen = new Set<string>(PRESET_DOMAINS);
		const out: string[] = [...PRESET_DOMAINS];

		for (const d of [...saved, ...extraDomains]) {
			if (!seen.has(d)) {
				seen.add(d);
				out.push(d);
			}
		}

		return out;
	});

	function startEdit(domain: string) {
		editing = domain;
		draft = cookies.get(domain);
	}

	function cancelEdit() {
		editing = null;
		draft = '';
	}

	function save(domain: string) {
		cookies.set(domain, draft);
		toast.success(t('cookies.savedToast', { site: domain }));
		cancelEdit();
	}

	function clearOne(domain: string) {
		cookies.clear(domain);
		toast.success(t('cookies.clearedToast', { site: domain }));
		if (editing === domain) {cancelEdit();}
	}

	function addCustom() {
		const domain = normalizeDomain(customDomain);

		if (!domain) {return;}

		if (!extraDomains.includes(domain)) {
			extraDomains = [...extraDomains, domain];
		}
		customDomain = '';
		startEdit(domain);
	}

	function clearAll() {
		cookies.clearAll();
		extraDomains = [];
		toast.success(t('cookies.clearedAllToast'));
		cancelEdit();
	}
</script>

<section class="rounded-lg border bg-white dark:border-zinc-700 dark:bg-zinc-800/50">
	<div class="border-b p-3 dark:border-zinc-700">
		<h4 class="flex items-center gap-2 text-base font-semibold">
			<Cookie class="h-4 w-4 text-amber-600" />
			{t('cookies.section')}
		</h4>
	</div>

	<div class="space-y-4 p-3 sm:p-4">
		<p class="text-muted-foreground text-xs">{t('cookies.desc')}</p>

		<!-- Warnings -->
		<div
			class="flex gap-2 rounded-lg border border-amber-300 bg-amber-50 p-3 text-xs text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-300"
		>
			<ShieldAlert class="mt-0.5 h-4 w-4 shrink-0" />
			<div class="space-y-1">
				<p class="font-medium">{t('cookies.warnTitle')}</p>
				<p>{t('cookies.warnThrowaway')}</p>
				<p>{t('cookies.warnLocal')}</p>
			</div>
		</div>

		<!-- How-to guide (collapsible) -->
		<div class="rounded-lg border dark:border-zinc-700">
			<button
				type="button"
				class="flex w-full items-center justify-between p-3 text-sm font-medium"
				onclick={() => (showGuide = !showGuide)}
			>
				<span>{t('cookies.guideToggle')}</span>
				<ChevronDown class="h-4 w-4 transition-transform {showGuide ? 'rotate-180' : ''}" />
			</button>
			{#if showGuide}
				<ol
					class="text-muted-foreground list-decimal space-y-1 p-3 pt-0 ps-8 text-xs"
				>
					<li>{t('cookies.guide.s1')}</li>
					<li>{t('cookies.guide.s2')}</li>
					<li>{t('cookies.guide.s3')}</li>
					<li>{t('cookies.guide.s4')}</li>
				</ol>
			{/if}
		</div>

		<!-- Per-site rows -->
		<div class="space-y-2">
			{#each rows as domain (domain)}
				<div class="rounded-lg bg-zinc-50 p-3 dark:bg-zinc-800/50">
					<div class="flex items-center justify-between gap-2">
						<div class="flex min-w-0 items-center gap-2">
							<span class="truncate text-sm font-medium">{domain}</span>
							{#if cookies.has(domain)}
								<span
									class="inline-flex items-center gap-1 rounded-full bg-green-100 px-2 py-0.5 text-[10px] font-medium text-green-700 dark:bg-green-900/30 dark:text-green-400"
								>
									<Check class="h-3 w-3" />
									{t('cookies.statusSaved')}
								</span>
							{:else}
								<span class="text-muted-foreground text-[10px]">{t('cookies.statusEmpty')}</span>
							{/if}
						</div>
						<div class="flex shrink-0 gap-1">
							<Button
								variant="outline"
								size="sm"
								class="h-8 cursor-pointer px-3"
								onclick={() => (editing === domain ? cancelEdit() : startEdit(domain))}
							>
								{cookies.has(domain) ? t('cookies.edit') : t('cookies.add')}
							</Button>
							{#if cookies.has(domain)}
								<Button
									variant="outline"
									size="sm"
									class="h-8 cursor-pointer px-2 hover:border-red-300 hover:bg-red-50 hover:text-red-700 dark:hover:border-red-700 dark:hover:bg-red-900/10 dark:hover:text-red-400"
									onclick={() => clearOne(domain)}
								>
									<Trash2 class="h-4 w-4" />
								</Button>
							{/if}
						</div>
					</div>

					{#if editing === domain}
						<div class="mt-3 space-y-2">
							<textarea
								bind:value={draft}
								spellcheck="false"
								autocomplete="off"
								rows="4"
								placeholder={t('cookies.placeholder', { site: domain })}
								class="border-input bg-background focus-visible:ring-ring w-full rounded-md border p-2 font-mono text-xs focus-visible:ring-1 focus-visible:outline-none"
							></textarea>
							<div class="flex gap-2">
								<Button size="sm" class="h-8 cursor-pointer px-4" onclick={() => save(domain)}>
									{t('cookies.save')}
								</Button>
								<Button
									variant="ghost"
									size="sm"
									class="h-8 cursor-pointer px-4"
									onclick={cancelEdit}
								>
									{t('cookies.cancel')}
								</Button>
							</div>
						</div>
					{/if}
				</div>
			{/each}
		</div>

		<!-- Add a custom site -->
		<div class="space-y-2">
			<Label class="text-sm font-medium">{t('cookies.customTitle')}</Label>
			<div class="flex gap-2">
				<input
					bind:value={customDomain}
					spellcheck="false"
					autocomplete="off"
					placeholder={t('cookies.customPlaceholder')}
					onkeydown={(e) => e.key === 'Enter' && addCustom()}
					class="border-input bg-background focus-visible:ring-ring h-9 flex-1 rounded-md border px-3 text-sm focus-visible:ring-1 focus-visible:outline-none"
				/>
				<Button size="sm" class="h-9 cursor-pointer px-4" onclick={addCustom}>
					<Plus class="me-1 h-4 w-4" />
					{t('cookies.customAdd')}
				</Button>
			</div>
		</div>

		{#if cookies.entries().length > 0}
			<Button
				variant="outline"
				size="sm"
				class="h-9 w-full cursor-pointer px-4 transition-colors hover:border-red-300 hover:bg-red-50 hover:text-red-700 dark:hover:border-red-700 dark:hover:bg-red-900/10 dark:hover:text-red-400"
				onclick={clearAll}
			>
				<Trash2 class="me-2 h-4 w-4" />
				{t('cookies.clearAll')}
			</Button>
		{/if}
	</div>
</section>
