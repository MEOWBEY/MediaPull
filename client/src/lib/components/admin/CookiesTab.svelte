<script lang="ts">
	import Cookie from '@lucide/svelte/icons/cookie';
	import Loader2 from '@lucide/svelte/icons/loader-2';
	import Plus from '@lucide/svelte/icons/plus';
	import Trash2 from '@lucide/svelte/icons/trash-2';
	import { onMount } from 'svelte';
	import { toast } from 'svelte-sonner';

	import { adminDelete, adminGet, adminPut } from '$lib/admin.svelte';
	import { Button } from '$lib/components/ui/button';
	import { i18n } from '$lib/i18n/index.svelte';

	type Entry = {
		domain: string;
		includeSubdomains: boolean;
		path: string;
		secure: boolean;
		expires: number;
		name: string;
		value: string;
	};

	type FileInfo = {
		path: string;
		exists: boolean;
		modified: string | null;
		expiredCount: number;
		entries: Entry[];
	};

	type Draft = {
		filePath: string;
		domain: string;
		includeSubdomains: boolean;
		path: string;
		secure: boolean;
		expires: number;
		name: string;
		value: string;
	};

	let files = $state<FileInfo[]>([]);
	let loaded = $state(false);
	let editing = $state<Draft | null>(null);
	let saving = $state(false);

	function emptyDraft(filePath: string): Draft {
		return {
			filePath,
			domain: '',
			includeSubdomains: true,
			path: '/',
			secure: true,
			expires: 0,
			name: '',
			value: ''
		};
	}

	async function load() {
		const { files: fileList } = await adminGet<{ files: FileInfo[] }>('/admin/cookies');

		files = fileList;
		loaded = true;
	}

	async function save(d: Draft) {
		if (!d.domain || !d.name) {
			return;
		}
		saving = true;
		try {
			await adminPut('/admin/cookies/entries', {
				path: d.filePath,
				domain: d.domain,
				name: d.name,
				value: d.value,
				cookiePath: d.path,
				secure: d.secure,
				includeSubdomains: d.includeSubdomains,
				expires: d.expires
			});
			toast.success(i18n.t('admin.cookies.saved', { domain: d.domain }));
			editing = null;
		} catch (e) {
			toast.error(e instanceof Error ? e.message : i18n.t('admin.cookies.saveFailed'));
		} finally {
			saving = false;
			await load();
		}
	}

	async function remove(f: FileInfo, e: Entry) {
		try {
			await adminDelete('/admin/cookies/entries', {
				path: f.path,
				domain: e.domain,
				name: e.name,
				cookie_path: e.path
			});
			toast.success(i18n.t('admin.cookies.removed', { name: e.name, domain: e.domain }));
		} catch (err) {
			toast.error(err instanceof Error ? err.message : i18n.t('admin.cookies.deleteFailed'));
		} finally {
			await load();
		}
	}

	function fmtExpires(ts: number): string {
		if (!ts) {
			return i18n.t('admin.cookies.session');
		}
		const d = new Date(ts * 1000);

		return `${d.toLocaleDateString()} ${d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
	}

	onMount(() => {
		void load();
	});
</script>

<div class="space-y-4">
	{#each files as file (file.path)}
		<section class="bg-card rounded-lg border p-4">
			<div class="flex flex-wrap items-center gap-x-3 gap-y-1">
				<Cookie class="text-signal h-4 w-4 shrink-0" aria-hidden="true" />
				<h2 class="min-w-0 flex-1 truncate font-mono text-sm font-semibold" title={file.path}>
					{file.path.split(/[\\/]/).pop()}
				</h2>
				{#if !file.exists}
					<span class="text-destructive text-xs font-medium">{i18n.t('admin.cookies.missing')}</span
					>
				{:else}
					<span class="text-muted-foreground text-xs">
						{i18n.t('admin.cookies.entries', {
							n: file.entries.length,
							time: file.modified?.replace('T', ' ').slice(0, 16) ?? ''
						})}
					</span>
					{#if file.expiredCount > 0}
						<span
							class="bg-amber-500/15 text-amber-500 rounded-sm px-1.5 py-0.5 text-[0.65rem] font-medium"
						>
							{i18n.t('admin.cookies.expired', { n: file.expiredCount })}
						</span>
					{/if}
				{/if}
			</div>

			{#if file.entries.length > 0}
				<div class="divide-border/70 mt-3 overflow-hidden rounded-md border divide-y">
					{#each file.entries as entry (entry.domain + entry.name + entry.path + entry.value)}
						<div class="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2">
							<div class="min-w-0 flex-1 basis-48">
								<p class="truncate font-mono text-sm">
									{entry.domain}
									<span class="text-muted-foreground"> / {entry.name}</span>
								</p>
								<p class="text-muted-foreground truncate font-mono text-xs" title={entry.value}>
									{entry.value || '(empty)'}
								</p>
							</div>
							<div class="flex shrink-0 items-center gap-2">
								<span class="text-muted-foreground font-mono text-[0.65rem]">
									{i18n.t(
										entry.includeSubdomains ? 'admin.cookies.subdomains' : 'admin.cookies.exact'
									)} ·&nbsp;
									{i18n.t(entry.secure ? 'admin.cookies.secure' : 'admin.cookies.insecure')} · {fmtExpires(
										entry.expires
									)}
								</span>
								<Button
									variant="outline"
									size="sm"
									class="h-7 cursor-pointer px-2"
									onclick={() => {
										editing = {
											filePath: file.path,
											domain: entry.domain,
											includeSubdomains: entry.includeSubdomains,
											path: entry.path,
											secure: entry.secure,
											expires: entry.expires,
											name: entry.name,
											value: entry.value
										};
									}}
								>
									{i18n.t('admin.cookies.edit')}
								</Button>
								<Button
									variant="ghost"
									size="sm"
									class="h-7 cursor-pointer px-1.5 hover:bg-destructive/10 hover:text-destructive"
									onclick={() => void remove(file, entry)}
									title={i18n.t('admin.cookies.deleteTitle', {
										name: entry.name,
										domain: entry.domain
									})}
								>
									<Trash2 class="h-3.5 w-3.5" aria-hidden="true" />
								</Button>
							</div>
						</div>
					{/each}
				</div>
			{:else}
				<p class="text-muted-foreground mt-3 text-xs">
					{i18n.t('admin.cookies.noEntries')}
				</p>
			{/if}

			<div class="mt-3 flex justify-end">
				<Button
					variant="outline"
					size="sm"
					class="h-8 cursor-pointer px-3"
					onclick={() => (editing = emptyDraft(file.path))}
					aria-expanded={editing?.filePath === file.path}
				>
					<Plus class="me-1 h-3.5 w-3.5" aria-hidden="true" />
					{i18n.t('admin.cookies.addEntry')}
				</Button>
			</div>

			{#if editing?.filePath === file.path}
				{@const d = editing!}
				<div class="mt-3 space-y-2 rounded-md border p-3">
					<div class="grid gap-2 sm:grid-cols-2">
						<label class="space-y-1">
							<span class="text-muted-foreground text-xs">{i18n.t('admin.cookies.domain')}</span>
							<input
								bind:value={d.domain}
								spellcheck="false"
								class="border-input bg-background focus-visible:ring-ring h-8 w-full rounded-md border px-2 font-mono text-xs focus-visible:ring-1 focus-visible:outline-none"
							/>
						</label>
						<label class="space-y-1">
							<span class="text-muted-foreground text-xs">{i18n.t('admin.cookies.name')}</span>
							<input
								bind:value={d.name}
								spellcheck="false"
								class="border-input bg-background focus-visible:ring-ring h-8 w-full rounded-md border px-2 font-mono text-xs focus-visible:ring-1 focus-visible:outline-none"
							/>
						</label>
						<label class="space-y-1 sm:col-span-2">
							<span class="text-muted-foreground text-xs">{i18n.t('admin.cookies.value')}</span>
							<textarea
								bind:value={d.value}
								rows="2"
								spellcheck="false"
								class="border-input bg-background focus-visible:ring-ring w-full rounded-md border p-2 font-mono text-xs focus-visible:ring-1 focus-visible:outline-none"
							></textarea>
						</label>
					</div>
					<div class="flex flex-wrap items-center gap-4 text-xs">
						<label class="flex cursor-pointer items-center gap-1.5">
							<input type="checkbox" bind:checked={d.secure} class="accent-foreground" />
							Secure
						</label>
						<label class="flex cursor-pointer items-center gap-1.5">
							<input type="checkbox" bind:checked={d.includeSubdomains} class="accent-foreground" />
							{i18n.t('admin.cookies.includeSubdomains')}
						</label>
					</div>
					<div class="flex gap-2">
						<Button
							size="sm"
							class="h-8 cursor-pointer px-3"
							onclick={() => void save(d)}
							disabled={saving || !d.domain || !d.name}
						>
							{#if saving}
								<Loader2 class="me-1 h-3.5 w-3.5 animate-spin" aria-hidden="true" />
							{/if}
							{i18n.t('admin.cookies.save')}
						</Button>
						<Button
							variant="ghost"
							size="sm"
							class="h-8 cursor-pointer px-3"
							onclick={() => (editing = null)}
						>
							{i18n.t('admin.cookies.cancel')}
						</Button>
					</div>
				</div>
			{/if}
		</section>
	{/each}

	{#if loaded && files.length === 0}
		<p class="text-muted-foreground p-4 text-sm">
			{i18n.t('admin.cookies.noFiles')}
		</p>
	{/if}

	<p class="text-muted-foreground text-xs">
		{i18n.t('admin.cookies.defaultsHint')}
	</p>
</div>
