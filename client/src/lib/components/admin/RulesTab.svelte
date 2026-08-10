<script lang="ts">
	import Plus from '@lucide/svelte/icons/plus';
	import Trash2 from '@lucide/svelte/icons/trash-2';
	import { onMount } from 'svelte';

	import { adminDelete, adminGet, adminPost } from '$lib/admin.svelte';
	import { Button } from '$lib/components/ui/button';
	import { i18n } from '$lib/i18n/index.svelte';

	type Rules = { bannedIps: string[]; blockedDomains: string[] };
	type UsageRow = { ip: string; total: number; [endpoint: string]: string | number };

	let bannedIps = $state<string[]>([]);
	let blockedDomains = $state<string[]>([]);
	let topIps = $state<UsageRow[]>([]);
	let newIp = $state('');
	let newDomain = $state('');
	let busy = $state(false);

	async function load() {
		const [rules, usage] = await Promise.allSettled([
			adminGet<Rules>('/admin/rules'),
			adminGet<{ topIps: UsageRow[] }>('/admin/usage')
		]);

		if (rules.status === 'fulfilled') {
			const { bannedIps: ips, blockedDomains: domains } = rules.value;

			bannedIps = ips;
			blockedDomains = domains;
		}
		if (usage.status === 'fulfilled') {
			const { topIps: tops } = usage.value;

			topIps = tops;
		}
	}

	async function addIp() {
		const v = newIp.trim();

		if (!v) {
			return;
		}
		busy = true;
		try {
			const { bannedIps: ips } = await adminPost<Rules>('/admin/rules/ips', { value: v });

			bannedIps = ips;
			newIp = '';
		} finally {
			busy = false;
		}
	}

	async function unbanIp(ip: string) {
		const { bannedIps: ips } = await adminDelete<Rules>('/admin/rules/ips', { ip });

		bannedIps = ips;
	}

	async function addDomain() {
		const v = newDomain.trim();

		if (!v) {
			return;
		}
		busy = true;
		try {
			const { blockedDomains: domains } = await adminPost<Rules>('/admin/rules/domains', {
				value: v
			});

			blockedDomains = domains;
			newDomain = '';
		} finally {
			busy = false;
		}
	}

	async function unblockDomain(domain: string) {
		const { blockedDomains: domains } = await adminDelete<Rules>('/admin/rules/domains', {
			domain
		});

		blockedDomains = domains;
	}

	onMount(() => {
		void load();
	});
</script>

<div class="grid gap-4 lg:grid-cols-2">
	<section class="bg-card rounded-lg border p-4">
		<h2 class="text-sm font-semibold">{i18n.t('admin.rules.bannedIps')}</h2>
		<p class="text-muted-foreground mb-3 mt-1 text-xs">
			{i18n.t('admin.rules.bannedIpsHint')}
		</p>
		<form
			class="mb-3 flex gap-2"
			onsubmit={(e) => {
				e.preventDefault();
				void addIp();
			}}
		>
			<input
				bind:value={newIp}
				spellcheck="false"
				autocomplete="off"
				placeholder="1.2.3.4"
				class="border-input bg-background focus-visible:ring-ring h-9 flex-1 rounded-md border px-3 font-mono text-sm focus-visible:ring-1 focus-visible:outline-none"
			/>
			<Button
				type="submit"
				size="sm"
				class="h-9 cursor-pointer px-3"
				disabled={busy || !newIp.trim()}
			>
				<Plus class="h-4 w-4" aria-hidden="true" />
			</Button>
		</form>
		<div class="divide-border/70 max-h-48 overflow-y-auto rounded-md border divide-y">
			{#if bannedIps.length === 0}
				<p class="text-muted-foreground p-3 text-xs">{i18n.t('admin.rules.noBans')}</p>
			{:else}
				{#each bannedIps as ip (ip)}
					<div class="flex items-center gap-2 px-3 py-1.5">
						<span class="min-w-0 flex-1 truncate font-mono text-sm">{ip}</span>
						<Button
							variant="ghost"
							size="sm"
							class="h-7 cursor-pointer px-1.5 hover:bg-destructive/10 hover:text-destructive"
							onclick={() => void unbanIp(ip)}
							title={i18n.t('admin.rules.unban', { ip })}
						>
							<Trash2 class="h-3.5 w-3.5" aria-hidden="true" />
						</Button>
					</div>
				{/each}
			{/if}
		</div>
	</section>

	<section class="bg-card rounded-lg border p-4">
		<h2 class="text-sm font-semibold">{i18n.t('admin.rules.blockedDomains')}</h2>
		<p class="text-muted-foreground mb-3 mt-1 text-xs">
			{i18n.t('admin.rules.blockedDomainsHint')}
		</p>
		<form
			class="mb-3 flex gap-2"
			onsubmit={(e) => {
				e.preventDefault();
				void addDomain();
			}}
		>
			<input
				bind:value={newDomain}
				spellcheck="false"
				autocomplete="off"
				placeholder="example.com"
				class="border-input bg-background focus-visible:ring-ring h-9 flex-1 rounded-md border px-3 font-mono text-sm focus-visible:ring-1 focus-visible:outline-none"
			/>
			<Button
				type="submit"
				size="sm"
				class="h-9 cursor-pointer px-3"
				disabled={busy || !newDomain.trim()}
			>
				<Plus class="h-4 w-4" aria-hidden="true" />
			</Button>
		</form>
		<div class="divide-border/70 max-h-48 overflow-y-auto rounded-md border divide-y">
			{#if blockedDomains.length === 0}
				<p class="text-muted-foreground p-3 text-xs">{i18n.t('admin.rules.noBlocked')}</p>
			{:else}
				{#each blockedDomains as domain (domain)}
					<div class="flex items-center gap-2 px-3 py-1.5">
						<span class="min-w-0 flex-1 truncate font-mono text-sm">{domain}</span>
						<Button
							variant="ghost"
							size="sm"
							class="h-7 cursor-pointer px-1.5 hover:bg-destructive/10 hover:text-destructive"
							onclick={() => void unblockDomain(domain)}
							title={i18n.t('admin.rules.unblock', { domain })}
						>
							<Trash2 class="h-3.5 w-3.5" aria-hidden="true" />
						</Button>
					</div>
				{/each}
			{/if}
		</div>
	</section>
</div>

<section class="bg-card rounded-lg border p-4">
	<h2 class="text-sm font-semibold">{i18n.t('admin.rules.heaviest')}</h2>
	<p class="text-muted-foreground mb-3 mt-1 text-xs">
		{i18n.t('admin.rules.heaviestHint')}
	</p>
	<div class="divide-border/70 overflow-hidden rounded-md border divide-y">
		{#if topIps.length === 0}
			<p class="text-muted-foreground p-3 text-xs">{i18n.t('admin.rules.noTraffic')}</p>
		{:else}
			{#each topIps as row (row.ip + String(row.total))}
				<div class="flex items-center gap-3 px-3 py-1.5">
					<span class="min-w-0 flex-1 truncate font-mono text-sm">{row.ip}</span>
					<span class="text-muted-foreground shrink-0 text-xs"
						>{i18n.t('admin.rules.hits', { n: row.total })}</span
					>
				</div>
			{/each}
		{/if}
	</div>
</section>
