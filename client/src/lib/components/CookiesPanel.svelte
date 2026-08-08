<script lang="ts">
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
	const { cookies } = appStore;

	// Famous sites shown by default; any custom domain the user saved is appended.
	const PRESET_DOMAINS = [
		'youtube.com',
		'instagram.com',
		'tiktok.com',
		'facebook.com',
		'x.com',
		'reddit.com',
		'vimeo.com',
		'twitch.tv',
		'twitter.com',
		'pixiv.net',
		'deviantart.com'
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
		// Transient dedupe set rebuilt each derivation — not reactive state.
		// eslint-disable-next-line svelte/prefer-svelte-reactivity
		const seen = new Set<string>(PRESET_DOMAINS);
		const base: string[] = [...PRESET_DOMAINS];

		for (const d of [...saved, ...extraDomains]) {
			if (!seen.has(d)) {
				seen.add(d);
				base.push(d);
			}
		}

		// Float sites that actually have a saved value to the top so a filled
		// cookie is pinned where it's easy to find/change, while empty presets
		// keep their original order below. Stable within each partition.
		return [...base].sort((a, b) => Number(cookies.has(b)) - Number(cookies.has(a)));
	});

	function isPreset(domain: string): boolean {
		return PRESET_DOMAINS.includes(domain);
	}

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
		// A custom (non-preset) row only exists to hold a value -- once cleared,
		// drop it from the transient list too, or it lingers as an empty row
		// with no other way to remove it.
		if (!isPreset(domain)) {
			extraDomains = extraDomains.filter((d) => d !== domain);
		}
		toast.success(t('cookies.clearedToast', { site: domain }));
		if (editing === domain) {
			cancelEdit();
		}
	}

	function addCustom() {
		const domain = normalizeDomain(customDomain);

		if (!domain) {
			return;
		}

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

<section class="bg-card rounded-lg border">
	<div class="border-border/60 border-b p-3">
		<h4 class="flex items-center gap-2 text-base font-semibold">
			<Cookie class="text-warning h-4 w-4" />
			{t('cookies.section')}
		</h4>
	</div>

	<div class="space-y-4 p-3 sm:p-4">
		<p class="text-muted-foreground text-xs">{t('cookies.desc')}</p>

		<!-- Warnings -->
		<div
			class="bg-warning/10 border-warning/40 text-warning-foreground dark:text-white flex gap-2 rounded-lg border p-3 text-xs"
		>
			<ShieldAlert class="mt-0.5 h-4 w-4 shrink-0" />
			<div class="space-y-1">
				<p class="font-medium">{t('cookies.warnTitle')}</p>
				<p>{t('cookies.warnThrowaway')}</p>
				<p>{t('cookies.warnLocal')}</p>
			</div>
		</div>

		<!-- How-to guide (collapsible) -->
		<div class="rounded-lg border">
			<button
				type="button"
				class="flex w-full items-center justify-between p-3 text-sm font-medium"
				onclick={() => (showGuide = !showGuide)}
				aria-expanded={showGuide}
				aria-controls="cookies-guide-steps"
			>
				<span>{t('cookies.guideToggle')}</span>
				<ChevronDown class="h-4 w-4 transition-transform {showGuide ? 'rotate-180' : ''}" />
			</button>
			{#if showGuide}
				<ol
					id="cookies-guide-steps"
					class="text-muted-foreground list-decimal space-y-1 p-3 pt-0 ps-8 text-xs"
				>
					<li>{t('cookies.guide.s1')}</li>
					<li>{t('cookies.guide.s2')}</li>
					<li>{t('cookies.guide.s3')}</li>
					<li>{t('cookies.guide.s4')}</li>
				</ol>
			{/if}
		</div>

		<!-- Add a custom site — first thing on the tab, so a new domain can be
		     typed before scrolling through the preset rows. -->
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

		<!-- Per-site rows first: entering/changing a cookie value is the primary
		     task here, so it sits at the top instead of below the warning + guide.
		     Divided list, same transfer-log rhythm as the video quality rows —
		     compact on mobile, one domain per line, status always visible at
		     the end (saved/empty).

		     Alignment: the domain name is its own flex-1 item (truncates instead
		     of pushing neighbors around). The "Saved" badge now lives inside the
		     button-group wrapper, right before the buttons, instead of tacked
		     onto the domain text. Since that button group is basically the same
		     width on every row, the badge sits at a consistent distance from the
		     right edge across all rows — that's the "fixed anchor" alignment.
		     On narrow screens the whole badge+buttons group wraps together as
		     one unit onto its own line, under the domain name. -->
		<div class="divide-border/70 overflow-hidden rounded-lg border divide-y">
			{#each rows as domain (domain)}
				<div class="hover:bg-muted/60 flex flex-wrap items-center gap-2 px-3 py-2 font-mono transition-colors">
					<span class="min-w-0 flex-1 truncate text-sm font-medium">{domain}</span>

					<div class="ms-auto flex shrink-0 flex-wrap items-center justify-end gap-1.5">
						{#if cookies.has(domain)}
							<span
								class="bg-primary/15 text-primary dark:text-primary shrink-0 whitespace-nowrap rounded-sm px-1.5 py-0.5 text-[0.65rem] font-medium"
							>
								{t('cookies.statusSaved')}
							</span>
						{/if}
						<Button
							variant="outline"
							size="sm"
							class="h-9 cursor-pointer px-3 sm:h-8"
							onclick={() => (editing === domain ? cancelEdit() : startEdit(domain))}
						>
							{cookies.has(domain) ? t('cookies.edit') : t('cookies.add')}
						</Button>
						{#if cookies.has(domain) || !isPreset(domain)}
							<Button
								variant="outline"
								size="sm"
								class="h-9 cursor-pointer px-2.5 hover:bg-destructive/10 hover:text-destructive hover:border-destructive/40 sm:h-8 sm:px-2"
								onclick={() => clearOne(domain)}
							>
								<Trash2 class="h-4 w-4" />
							</Button>
						{/if}
					</div>

					{#if editing === domain}
						<div class="mt-2.5 w-full space-y-2">
							<textarea
								bind:value={draft}
								spellcheck="false"
								autocomplete="off"
								rows="4"
								placeholder={t('cookies.placeholder', { site: domain })}
								class="border-input bg-card focus-visible:ring-ring w-full rounded-md border p-2 font-mono text-xs focus-visible:ring-1 focus-visible:outline-none"
							></textarea>
							<div class="flex gap-2">
								<Button
									size="sm"
									class="h-9 cursor-pointer px-4 sm:h-8"
									onclick={() => save(domain)}
								>
									{t('cookies.save')}
								</Button>
								<Button
									variant="ghost"
									size="sm"
									class="h-9 cursor-pointer px-4 sm:h-8"
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

		{#if cookies.entries().length > 0}
			<Button
				variant="outline"
				size="sm"
				class="h-9 w-full cursor-pointer px-4 transition-colors hover:bg-destructive/10 hover:text-destructive hover:border-destructive/40"
				onclick={clearAll}
			>
				<Trash2 class="me-2 h-4 w-4" />
				{t('cookies.clearAll')}
			</Button>
		{/if}
	</div>
</section>
