<script lang="ts">
	import Cookies from '@lucide/svelte/icons/cookie';
	import FileClock from '@lucide/svelte/icons/file-clock';
	import Gauge from '@lucide/svelte/icons/gauge';
	import Loader2 from '@lucide/svelte/icons/loader-2';
	import Lock from '@lucide/svelte/icons/lock';
	import LogOut from '@lucide/svelte/icons/log-out';
	import ScrollText from '@lucide/svelte/icons/scroll-text';
	import Shield from '@lucide/svelte/icons/shield';
	import ShieldBan from '@lucide/svelte/icons/shield-ban';
	import SlidersHorizontal from '@lucide/svelte/icons/sliders-horizontal';
	import { onMount } from 'svelte';

	import { adminSession, checkSession, login, logout } from '$lib/admin.svelte';
	import CookiesTab from '$lib/components/admin/CookiesTab.svelte';
	import EnvTab from '$lib/components/admin/EnvTab.svelte';
	import JobsTab from '$lib/components/admin/JobsTab.svelte';
	import LogsTab from '$lib/components/admin/LogsTab.svelte';
	import OverviewTab from '$lib/components/admin/OverviewTab.svelte';
	import RulesTab from '$lib/components/admin/RulesTab.svelte';
	import { Button } from '$lib/components/ui/button';
	import { i18n } from '$lib/i18n/index.svelte';

	type TabId = 'overview' | 'logs' | 'jobs' | 'rules' | 'env' | 'cookies';

	let activeTab = $state<TabId>('overview');
	let busy = $state(false);
	let error = $state('');

	const tabs: { id: TabId; label: string; icon: typeof Gauge }[] = [
		{ id: 'overview', label: i18n.t('admin.tabs.overview'), icon: Gauge },
		{ id: 'logs', label: i18n.t('admin.tabs.logs'), icon: ScrollText },
		{ id: 'jobs', label: i18n.t('admin.tabs.jobs'), icon: FileClock },
		{ id: 'rules', label: i18n.t('admin.tabs.rules'), icon: ShieldBan },
		{ id: 'env', label: i18n.t('admin.tabs.env'), icon: SlidersHorizontal },
		{ id: 'cookies', label: i18n.t('admin.tabs.cookies'), icon: Cookies }
	];

	let username = $state('');
	let password = $state('');

	// svelte:head's <title> re-renders on locale change, but Chromium doesn't
	// reflect that in the tab without a manual document.title write — do it
	// here so switching language updates the tab immediately.
	$effect(() => {
		if (typeof document !== 'undefined') {
			document.title = i18n.t('admin.titleTab');
		}
	});

	async function signIn() {
		busy = true;
		error = '';
		try {
			await login(username.trim(), password);
			password = '';
		} catch (e) {
			error = e instanceof Error ? e.message : 'Sign-in failed';
		} finally {
			busy = false;
		}
	}

	async function signOut() {
		await logout();
		activeTab = 'overview';
	}

	onMount(() => {
		void checkSession();
	});
</script>

<svelte:head>
	<title>{i18n.t('admin.titleTab')}</title>
</svelte:head>

<div dir="ltr" class="flex w-full max-w-7xl flex-col gap-6 px-4 py-8">
	{#if adminSession.loggedIn}
		<header class="flex flex-wrap items-center justify-between gap-3">
			<div class="flex items-center gap-2">
				<Shield class="text-signal h-5 w-5" aria-hidden="true" />
				<h1 class="font-heading text-xl font-bold tracking-tight">{i18n.t('admin.title')}</h1>
			</div>
			<div class="flex items-center gap-3">
				<span class="text-muted-foreground font-mono text-xs" title={i18n.t('admin.operatorTitle')}>
					{adminSession.username}
				</span>
				<Button
					variant="outline"
					size="sm"
					class="h-9 cursor-pointer px-3"
					onclick={signOut}
					title={i18n.t('admin.signOut')}
				>
					<LogOut class="me-1 h-4 w-4" aria-hidden="true" />
					{i18n.t('admin.signOut')}
				</Button>
			</div>
		</header>

		<nav
			class="border-border/70 overflow-x-auto rounded-md border font-mono text-xs"
			aria-label={i18n.t('admin.sectionsLabel')}
		>
			<div class="flex min-w-max">
				{#each tabs as tab, i (tab.id)}
					<button
						type="button"
						onclick={() => (activeTab = tab.id)}
						aria-current={activeTab === tab.id ? 'page' : undefined}
						class={[
							'flex h-9 cursor-pointer items-center gap-1.5 px-3.5 transition-colors',
							i > 0 && 'border-border/70 border-s',
							activeTab === tab.id
								? 'bg-signal/15 text-signal font-semibold'
								: 'text-muted-foreground hover:bg-muted hover:text-foreground'
						]}
					>
						<tab.icon class="h-4 w-4" aria-hidden="true" />
						{tab.label}
					</button>
				{/each}
			</div>
		</nav>

		{#if activeTab === 'overview'}
			<OverviewTab />
		{:else if activeTab === 'logs'}
			<LogsTab />
		{:else if activeTab === 'jobs'}
			<JobsTab />
		{:else if activeTab === 'rules'}
			<RulesTab />
		{:else if activeTab === 'env'}
			<EnvTab />
		{:else}
			<CookiesTab />
		{/if}
	{:else if adminSession.checked}
		<div class="mx-auto flex w-full max-w-md flex-col gap-2">
			<div class="flex items-center gap-2">
				<Shield class="text-signal h-5 w-5" aria-hidden="true" />
				<h1 class="font-heading text-lg font-bold tracking-tight">{i18n.t('admin.title')}</h1>
			</div>
			<div class="bg-card space-y-4 rounded-lg border p-5 shadow-sm">
				<form
					class="space-y-3"
					onsubmit={(e) => {
						e.preventDefault();
						void signIn();
					}}
				>
					<div class="space-y-1.5">
						<label for="admin-username" class="text-sm font-medium"
							>{i18n.t('admin.username')}</label
						>
						<input
							id="admin-username"
							bind:value={username}
							autocomplete="username"
							spellcheck="false"
							class="border-input bg-background focus-visible:ring-ring h-9 w-full rounded-md border px-3 text-sm focus-visible:ring-1 focus-visible:outline-none"
						/>
					</div>
					<div class="space-y-1.5">
						<label for="admin-password" class="text-sm font-medium"
							>{i18n.t('admin.password')}</label
						>
						<input
							id="admin-password"
							type="password"
							bind:value={password}
							autocomplete="current-password"
							class="border-input bg-background focus-visible:ring-ring h-9 w-full rounded-md border px-3 text-sm focus-visible:ring-1 focus-visible:outline-none"
						/>
					</div>
					{#if error}
						<p class="text-destructive flex items-center gap-1.5 text-sm" role="alert">
							<Lock class="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
							{error}
						</p>
					{/if}
					<Button
						type="submit"
						class="h-9 w-full cursor-pointer"
						disabled={busy || !username || !password}
					>
						{#if busy}
							<Loader2 class="me-1 h-4 w-4 animate-spin" aria-hidden="true" />
						{/if}
						{i18n.t('admin.signIn')}
					</Button>
				</form>
			</div>
			<p class="text-muted-foreground text-xs">
				{i18n.t('admin.disabledHint')}
			</p>
		</div>
	{:else}
		<div class="flex justify-center py-16">
			<Loader2 class="text-muted-foreground h-6 w-6 animate-spin" aria-hidden="true" />
		</div>
	{/if}

	{#if adminSession.loggedIn}
		{#if activeTab !== 'overview' && activeTab !== 'logs' && activeTab !== 'cookies'}
			<p class="text-muted-foreground text-xs">
				{i18n.t('admin.immediateHint')}
			</p>
		{/if}
	{/if}
</div>
