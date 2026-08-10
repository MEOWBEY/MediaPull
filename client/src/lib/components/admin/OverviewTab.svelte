<script lang="ts">
	import AlertTriangle from '@lucide/svelte/icons/alert-triangle';
	import Clock from '@lucide/svelte/icons/clock';
	import Cookie from '@lucide/svelte/icons/cookie';
	import Download from '@lucide/svelte/icons/download';
	import RefreshCw from '@lucide/svelte/icons/refresh-cw';
	import RotateCcw from '@lucide/svelte/icons/rotate-ccw';
	import ShieldBan from '@lucide/svelte/icons/shield-ban';
	import Tag from '@lucide/svelte/icons/tag';
	import Trash2 from '@lucide/svelte/icons/trash-2';
	import { onMount } from 'svelte';
	import { toast } from 'svelte-sonner';

	import { adminGet, adminPost } from '$lib/admin.svelte';
	import { Button } from '$lib/components/ui/button';
	import { i18n } from '$lib/i18n/index.svelte';

	type Overview = {
		version: string;
		uptimeSeconds: number;
		pendingEnvChanges: number;
	};

	type Rules = { bannedIps: string[]; blockedDomains: string[] };
	type CookieFiles = {
		files: {
			path: string;
			exists: boolean;
			expiredCount: number;
			modified: string | null;
			entries: { domain: string; name: string }[];
		}[];
	};
	type Jobs = { jobs: { type: string; status: string }[] };
	type System = {
		branch: string | null;
		behind: number | null;
		dirty: boolean;
		gitAvailable: boolean;
		updateAvailable: boolean;
		uninstallAvailable: boolean;
	};

	let overview = $state<Overview | null>(null);
	let rules = $state<Rules | null>(null);
	let cookies = $state<CookieFiles | null>(null);
	let jobs = $state<Jobs | null>(null);
	let system = $state<System | null>(null);
	let purging = $state(false);
	let restartBusy = $state(false);
	let updateBusy = $state(false);
	let uninstallArmed = $state(false);
	let uninstallText = $state('');
	let uninstallBusy = $state(false);
	let restartDetail = $state('');

	function fmtUptime(secs: number): string {
		const d = Math.floor(secs / 86400);
		const h = Math.floor((secs % 86400) / 3600);
		const m = Math.floor((secs % 3600) / 60);

		if (d > 0) {
			return `${d}d ${h}h`;
		}
		if (h > 0) {
			return `${h}h ${m}m`;
		}

		return `${m}m`;
	}

	async function load() {
		const [o, r, c, j, s] = await Promise.allSettled([
			adminGet<Overview>('/admin/overview'),
			adminGet<Rules>('/admin/rules'),
			adminGet<CookieFiles>('/admin/cookies'),
			adminGet<Jobs>('/admin/jobs'),
			adminGet<System>('/admin/system')
		]);

		if (o.status === 'fulfilled') {
			overview = o.value;
		}
		if (r.status === 'fulfilled') {
			rules = r.value;
		}
		if (c.status === 'fulfilled') {
			cookies = c.value;
		}
		if (j.status === 'fulfilled') {
			jobs = j.value;
		}
		if (s.status === 'fulfilled') {
			system = s.value;
		}
	}

	async function restartService() {
		restartBusy = true;
		try {
			const r = await adminPost<{ restarted: boolean; detail: string | null }>('/admin/restart');

			restartDetail = r.detail ?? '';
			if (r.restarted) {
				toast.success(i18n.t('admin.env.restarting'));
			}
		} catch (e) {
			restartDetail = e instanceof Error ? e.message : '';
		} finally {
			restartBusy = false;
		}
	}

	async function runUpdate() {
		updateBusy = true;
		try {
			const r = await adminPost<{ started: boolean; detail: string }>('/admin/update');

			if (r.started) {
				toast.success(i18n.t('admin.system.started'));
			} else {
				toast.error(r.detail);
			}
		} catch (e) {
			toast.error(e instanceof Error ? e.message : i18n.t('admin.system.unknown'));
		} finally {
			updateBusy = false;
		}
	}

	async function runUninstall() {
		uninstallBusy = true;
		try {
			const r = await adminPost<{ started: boolean; detail: string }>('/admin/uninstall', {
				confirm: uninstallText
			});

			if (r.started) {
				toast.success(i18n.t('admin.system.started'));
			} else {
				toast.error(r.detail);
			}
		} catch (e) {
			toast.error(e instanceof Error ? e.message : i18n.t('admin.system.unknown'));
		} finally {
			uninstallBusy = false;
			uninstallArmed = false;
			uninstallText = '';
		}
	}

	async function purge() {
		purging = true;
		try {
			await adminPost('/admin/cache/purge');
		} finally {
			purging = false;
		}
	}

	onMount(() => {
		void load();
	});
</script>

<div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
	<div class="bg-card space-y-1 rounded-lg border p-4">
		<div
			class="text-muted-foreground flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide"
		>
			<Tag class="h-3.5 w-3.5" aria-hidden="true" />
			{i18n.t('admin.overview.server')}
		</div>
		<p class="font-mono text-2xl font-bold" title="Backend version">
			{overview?.version ?? '…'}
		</p>
		<p class="text-muted-foreground flex items-center gap-1.5 text-xs">
			<Clock class="h-3.5 w-3.5" aria-hidden="true" />
			{i18n.t('admin.overview.up', { time: overview ? fmtUptime(overview.uptimeSeconds) : '…' })}
		</p>
	</div>

	<div class="bg-card space-y-1 rounded-lg border p-4">
		<div
			class="text-muted-foreground flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide"
		>
			<ShieldBan class="h-3.5 w-3.5" aria-hidden="true" />
			{i18n.t('admin.overview.rules')}
		</div>
		<p class="font-mono text-2xl font-bold">
			{rules ? rules.bannedIps.length : '…'}
			<span class="text-muted-foreground text-sm font-normal"
				>{i18n.t('admin.overview.ipsBanned')}</span
			>
		</p>
		<p class="text-muted-foreground text-xs">
			{i18n.t('admin.overview.domainsBlocked', { n: rules ? rules.blockedDomains.length : '…' })}
		</p>
	</div>

	<div class="bg-card space-y-1 rounded-lg border p-4">
		<div
			class="text-muted-foreground flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide"
		>
			<Cookie class="h-3.5 w-3.5" aria-hidden="true" />
			{i18n.t('admin.overview.cookies')}
		</div>
		<p class="font-mono text-2xl font-bold">
			{#each cookies?.files ?? [] as file (file.path)}
				{#if !file.exists}
					<span class="text-destructive" title="{file.path} is missing"
						>{i18n.t('admin.overview.cookieMissing')}</span
					>
				{:else if file.expiredCount > 0}
					<span class="text-amber-500" title="{file.expiredCount} expired entries in {file.path}">
						{i18n.t('admin.overview.cookieExpired', { n: file.expiredCount })}
					</span>
				{:else}
					<span class="text-emerald-500" title={file.path}
						>{i18n.t('admin.overview.cookieFresh')}</span
					>
				{/if}
			{:else}
				<span class="text-muted-foreground text-sm font-normal"
					>{i18n.t('admin.overview.cookiesNotConfigured')}</span
				>
			{/each}
		</p>
	</div>

	<div class="bg-card space-y-1 rounded-lg border p-4">
		<div
			class="text-muted-foreground flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide"
		>
			<RefreshCw class="h-3.5 w-3.5" aria-hidden="true" />
			{i18n.t('admin.overview.jobs')}
		</div>
		<p class="font-mono text-2xl font-bold">
			{jobs ? jobs.jobs.filter((j) => j.status === 'queued' || j.status === 'running').length : '…'}
			<span class="text-muted-foreground text-sm font-normal"
				>{i18n.t('admin.overview.jobsActive')}</span
			>
		</p>
		<p class="text-muted-foreground text-xs">
			{i18n.t('admin.overview.jobsTotal', { n: jobs ? jobs.jobs.length : '…' })}
		</p>
	</div>
</div>

{#if overview?.pendingEnvChanges}
	<div
		class="border-amber-500/40 bg-amber-500/10 flex items-start gap-2 rounded-lg border p-3 text-sm"
	>
		<AlertTriangle class="text-amber-500 mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
		<div>
			<span class="font-medium">{i18n.t('admin.overview.envChangedTitle')}</span>&nbsp;
			<span class="text-muted-foreground">
				{i18n.t('admin.overview.envChangedCount', { n: overview.pendingEnvChanges })}
				{i18n.t('admin.open')}&nbsp;
				<strong>{i18n.t('admin.tabs.env')}</strong>&nbsp;
				{i18n.t('admin.overview.envChangedReview')}
			</span>
		</div>
	</div>
{/if}

<div class="flex items-center justify-between gap-3">
	<h2 class="font-heading text-sm font-semibold">{i18n.t('admin.overview.maintenance')}</h2>
	<Button
		variant="outline"
		size="sm"
		class="h-9 cursor-pointer px-3"
		onclick={purge}
		disabled={purging}
		title={i18n.t('admin.overview.purgeTitle')}
	>
		<RefreshCw class="me-1 h-4 w-4 {purging ? 'animate-spin' : ''}" aria-hidden="true" />
		{i18n.t('admin.overview.purge')}
	</Button>
</div>
<p class="text-muted-foreground text-xs">
	{i18n.t('admin.overview.purgeHint')}
</p>

{#if system}
	<div class="bg-card rounded-lg border p-4">
		<div class="flex flex-wrap items-center justify-between gap-3">
			<div class="min-w-0">
				<h2 class="font-heading text-sm font-semibold">{i18n.t('admin.system.title')}</h2>
				<p class="text-muted-foreground font-mono text-xs">
					{#if system.branch}
						<span class="text-signal">{system.branch}</span>&nbsp;·&nbsp;
						{system.behind === null
							? i18n.t('admin.system.unknown')
							: system.behind > 0
								? i18n.t('admin.system.behind', { n: system.behind })
								: i18n.t('admin.system.upToDate')}
						{#if system.dirty}
							&nbsp;·&nbsp;{i18n.t('admin.system.dirty')}
						{/if}
					{:else}
						{i18n.t('admin.system.unknown')}
					{/if}
				</p>
			</div>
			<div class="flex flex-wrap items-center gap-2">
				<Button
					variant="outline"
					size="sm"
					class="h-9 cursor-pointer px-3"
					onclick={restartService}
					disabled={restartBusy}
					title={i18n.t('admin.system.updateHint')}
				>
					<RotateCcw class="me-1 h-4 w-4 {restartBusy ? 'animate-spin' : ''}" aria-hidden="true" />
					{i18n.t('admin.env.restart')}
				</Button>
				{#if system.updateAvailable}
					<Button
						variant="outline"
						size="sm"
						class="h-9 cursor-pointer px-3"
						onclick={runUpdate}
						disabled={updateBusy}
						title={i18n.t('admin.system.updateHint')}
					>
						<Download class="me-1 h-4 w-4" aria-hidden="true" />
						{i18n.t('admin.system.update')}
					</Button>
				{/if}
				{#if system.uninstallAvailable}
					<Button
						variant="outline"
						size="sm"
						class="h-9 cursor-pointer px-3 hover:bg-destructive/10 hover:text-destructive hover:border-destructive/40"
						onclick={() => (uninstallArmed = true)}
						title={i18n.t('admin.system.uninstallHint')}
					>
						<Trash2 class="me-1 h-4 w-4" aria-hidden="true" />
						{i18n.t('admin.system.uninstall')}
					</Button>
				{/if}
			</div>
		</div>

		{#if uninstallArmed}
			<div class="mt-3 flex flex-wrap items-center gap-2 rounded-md border border-destructive/30 p-3">
				<span class="text-destructive flex-1 text-xs">{i18n.t('admin.system.uninstallHint')}</span>
				<input
					bind:value={uninstallText}
					spellcheck="false"
					placeholder={i18n.t('admin.system.confirmLabel')}
					class="border-input bg-background focus-visible:ring-ring h-8 w-56 rounded-md border px-2 font-mono text-xs focus-visible:ring-1 focus-visible:outline-none"
				/>
				<Button
					size="sm"
					variant="destructive"
					class="h-8 cursor-pointer px-3"
					disabled={uninstallBusy || uninstallText !== 'uninstall'}
					onclick={runUninstall}
				>
					{i18n.t('admin.system.confirm')}
				</Button>
				<Button
					variant="ghost"
					size="sm"
					class="h-8 cursor-pointer px-3"
					onclick={() => {
						uninstallArmed = false;
						uninstallText = '';
					}}
				>
					{i18n.t('admin.cookies.cancel')}
				</Button>
			</div>
		{/if}

		{#if restartDetail}
			<p class="text-muted-foreground mt-2 text-xs">{restartDetail}</p>
		{/if}
	</div>
{/if}
