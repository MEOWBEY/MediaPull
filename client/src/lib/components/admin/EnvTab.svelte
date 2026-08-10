<script lang="ts">
	import Eye from '@lucide/svelte/icons/eye';
	import EyeOff from '@lucide/svelte/icons/eye-off';
	import Loader2 from '@lucide/svelte/icons/loader-2';
	import RotateCcw from '@lucide/svelte/icons/rotate-ccw';
	import Save from '@lucide/svelte/icons/save';
	import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
	import Undo2 from '@lucide/svelte/icons/undo-2';
	import { onMount } from 'svelte';
	import { toast } from 'svelte-sonner';

	import { adminGet, adminPost } from '$lib/admin.svelte';
	import { Button } from '$lib/components/ui/button';
	import Switch from '$lib/components/ui/switch/switch.svelte';
	import { i18n } from '$lib/i18n/index.svelte';

	type EnvKey = {
		key: string;
		value: string;
		running: string | null;
		secret: boolean;
		type: string;
		min: number | null;
		max: number | null;
		default: string | number | boolean | null;
		help: string | null;
		changed: boolean;
	};

	let keys = $state<EnvKey[]>([]);
	let loaded = $state(false);
	let drafts = $state<Record<string, string>>({});
	let revealed = $state<Record<string, boolean>>({});
	let saving = $state(false);
	let preview = $state<{
		errors: { key: string; message: string }[];
		warnings: { key: string; type: string; message: string }[];
	} | null>(null);
	let restarting = $state(false);

	async function load() {
		const { keys: keyList } = await adminGet<{ keys: EnvKey[] }>('/admin/env');

		keys = keyList;
		loaded = true;
		drafts = {};
		preview = null;
	}

	function draftOf(k: EnvKey): string {
		return drafts[k.key] ?? k.value;
	}

	function isDirty(k: EnvKey): boolean {
		return drafts[k.key] !== undefined && drafts[k.key] !== k.value;
	}

	function toggleReveal(k: EnvKey) {
		revealed = { ...revealed, [k.key]: !revealed[k.key] };
	}

	function isNumeric(k: EnvKey): boolean {
		return k.type === 'integer' || k.type === 'number';
	}

	function isInteger(k: EnvKey): boolean {
		return k.type === 'integer';
	}

	function isBoolean(k: EnvKey): boolean {
		return k.type === 'boolean';
	}

	function boolOf(k: EnvKey): boolean {
		return draftOf(k) === 'true';
	}

	function setBool(k: EnvKey, next: boolean) {
		drafts = { ...drafts, [k.key]: next ? 'true' : 'false' };
	}

	function hasDefault(k: EnvKey): boolean {
		return k.default !== undefined && k.default !== null;
	}

	function restoreDefault(k: EnvKey) {
		drafts = { ...drafts, [k.key]: hasDefault(k) ? String(k.default) : '' };
	}

	function masked(v: string): string {
		return v ? '••••••••' : i18n.t('admin.env.emptyValue');
	}

	function rangeText(k: EnvKey): string | null {
		if (!isNumeric(k) || (k.min === null && k.max === null)) {
			return null;
		}
		if (k.min !== null && k.max !== null) {
			return `${k.min} – ${k.max}`;
		}
		if (k.min !== null) {
			return `≥ ${k.min}`;
		}

		return `≤ ${k.max}`;
	}

	function numericInvalid(k: EnvKey): boolean {
		if (!isNumeric(k)) {
			return false;
		}
		const raw = draftOf(k).trim();

		if (raw === '') {
			return false;
		}
		const v = Number(raw);

		if (!Number.isFinite(v) || (isInteger(k) && !Number.isInteger(v))) {
			return true;
		}
		if (k.min !== null && v < k.min) {
			return true;
		}
		if (k.max !== null && v > k.max) {
			return true;
		}

		return false;
	}

	function guideTitle(k: EnvKey): string | undefined {
		const parts: string[] = [];

		if (k.help) {
			parts.push(k.help);
		}
		const range = rangeText(k);

		if (range) {
			parts.push(i18n.t('admin.env.range', { min: k.min ?? '–∞', max: k.max ?? '∞' }));
		}

		return parts.length > 0 ? parts.join(' — ') : undefined;
	}

	const changeCount = $derived(keys.filter(isDirty).length);
	const invalidCount = $derived(keys.filter(numericInvalid).length);

	async function save() {
		if (changeCount === 0 || invalidCount > 0) {
			return;
		}
		saving = true;
		preview = null;
		try {
			const updates: Record<string, string> = {};

			for (const k of keys) {
				if (isDirty(k)) {
					updates[k.key] = draftOf(k);
				}
			}
			preview = await adminPost('/admin/env/preview', { updates });
			const result = preview;

			if (!result || result.errors.length > 0) {
				return;
			}
			const { written } = await adminPost<{ written: Record<string, string> }>('/admin/env/apply', {
				updates
			});

			toast.success(i18n.t('admin.env.saved', { n: Object.keys(written).length }));
		} finally {
			saving = false;
			await load();
		}
	}

	async function restart() {
		restarting = true;
		try {
			const { restarted, detail } = await adminPost<{ restarted: boolean; detail: string | null }>(
				'/admin/restart'
			);

			if (restarted) {
				toast.success(i18n.t('admin.env.restarting'));
			} else {
				toast.info(detail ?? i18n.t('admin.env.noRestart'));
			}
		} finally {
			restarting = false;
		}
	}

	onMount(() => {
		void load();
	});
</script>

<div class="flex flex-wrap items-center justify-between gap-2">
	<h2 class="font-heading text-sm font-semibold">{i18n.t('admin.env.title')}</h2>
	<div class="flex items-center gap-2">
		<Button
			size="sm"
			class="h-9 cursor-pointer px-3"
			onclick={save}
			disabled={saving || changeCount === 0 || invalidCount > 0}
			title={invalidCount > 0 ? i18n.t('admin.env.invalidHint') : undefined}
		>
			{#if saving}
				<Loader2 class="me-1 h-4 w-4 animate-spin" aria-hidden="true" />
			{:else}
				<Save class="me-1 h-4 w-4" aria-hidden="true" />
			{/if}
			{i18n.t('admin.env.save')}
		</Button>
		<Button
			variant="ghost"
			size="sm"
			class="h-9 cursor-pointer px-3"
			onclick={restart}
			disabled={restarting}
			title={i18n.t('admin.env.restartTitle')}
		>
			<RotateCcw class="me-1 h-4 w-4 {restarting ? 'animate-spin' : ''}" aria-hidden="true" />
			{i18n.t('admin.env.restart')}
		</Button>
	</div>
</div>

{#if changeCount > 0}
	<p class="text-muted-foreground text-xs">
		{i18n.t('admin.env.unsaved', { n: changeCount })}{#if invalidCount > 0}
			&nbsp;·&nbsp;<span class="text-destructive"
				>{i18n.t('admin.env.invalid', { n: invalidCount })}</span
			>
		{/if}
	</p>
{/if}

{#if preview}
	<div class="space-y-2">
		{#if preview.errors.length > 0}
			<div
				class="border-destructive/40 bg-destructive/10 rounded-lg border p-3 text-sm"
				role="alert"
			>
				<p class="font-medium">{i18n.t('admin.env.fixBeforeApplying')}</p>
				<ul class="text-muted-foreground mt-1 list-disc space-y-0.5 ps-5">
					{#each preview.errors as err (err.key + err.message)}
						<li><span class="font-mono">{err.key}</span> — {err.message}</li>
					{/each}
				</ul>
			</div>
		{/if}
		{#each preview.warnings as w (w.key + w.message)}
			<div
				class="flex items-start gap-2 rounded-lg border p-3 text-sm
					{w.type === 'warn' ? 'border-amber-500/40 bg-amber-500/10' : 'bg-card'}"
			>
				<TriangleAlert class="text-amber-500 mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
				<p class="text-muted-foreground">
					<span class="font-mono">{w.key}</span> — {w.message}
				</p>
			</div>
		{/each}
	</div>
{/if}

{#if loaded}
	<div class="bg-card overflow-hidden rounded-lg border">
		<div class="divide-border/70 divide-y">
			{#each keys as k (k.key)}
				<div class="flex flex-wrap items-center gap-x-3 gap-y-2 px-3 py-2.5">
					<div class="flex min-w-0 flex-1 basis-56 flex-col gap-0.5">
						<div class="flex items-center gap-2">
							<span class="font-mono text-sm font-semibold" title={k.help ?? undefined}>
								{k.key}
							</span>
							{#if k.changed}
								<span
									class="bg-amber-500/15 text-amber-500 shrink-0 rounded-sm px-1.5 py-0.5 text-[0.65rem] font-medium"
									title={i18n.t('admin.env.needsRestartTitle')}
								>
									{i18n.t('admin.env.needsRestart')}
								</span>
							{/if}
						</div>
						{#if rangeText(k)}
							<span class="text-muted-foreground font-mono text-[0.65rem]">
								{rangeText(k)}
							</span>
						{/if}
					</div>

					<div class="flex min-w-0 flex-1 basis-64 items-center gap-1.5">
						{#if isBoolean(k)}
							<div class="flex h-8 w-full items-center gap-2">
								<Switch
									checked={boolOf(k)}
									onCheckedChange={(v) => setBool(k, Boolean(v))}
									aria-label={k.key}
									title={k.help ?? undefined}
								/>
								<span
									class="font-mono text-xs {boolOf(k) ? 'text-signal' : 'text-muted-foreground'}"
								>
									{boolOf(k) ? 'true' : 'false'}
								</span>
							</div>
						{:else if k.secret}
							<div class="relative flex min-w-0 flex-1 items-center">
								<input
									readonly={!revealed[k.key]}
									value={revealed[k.key] ? draftOf(k) : masked(draftOf(k))}
									type="text"
									spellcheck="false"
									autocomplete="off"
									title={guideTitle(k)}
									class="border-input bg-background focus-visible:ring-ring h-8 min-w-0 w-full rounded-md border pe-9 px-2 font-mono text-xs focus-visible:ring-1 focus-visible:outline-none"
								/>
								<Button
									variant="ghost"
									size="sm"
									class="absolute top-1/2 end-1 h-6 w-6 -translate-y-1/2 cursor-pointer px-0 text-muted-foreground"
									onclick={() => toggleReveal(k)}
									title={revealed[k.key]
										? i18n.t('admin.env.hide', { key: k.key })
										: i18n.t('admin.env.reveal', { key: k.key })}
								>
									{#if revealed[k.key]}
										<EyeOff class="h-3.5 w-3.5" aria-hidden="true" />
									{:else}
										<Eye class="h-3.5 w-3.5" aria-hidden="true" />
									{/if}
								</Button>
							</div>
						{:else}
							<input
								value={draftOf(k)}
								type={isNumeric(k) ? 'number' : 'text'}
								min={k.min ?? undefined}
								max={k.max ?? undefined}
								step={isInteger(k) ? '1' : isNumeric(k) ? 'any' : undefined}
								oninput={(e) => {
									drafts = { ...drafts, [k.key]: e.currentTarget.value };
								}}
								spellcheck="false"
								autocomplete="off"
								title={guideTitle(k)}
								class="border-input bg-background focus-visible:ring-ring h-8 min-w-0 flex-1 rounded-md border px-2 font-mono text-xs focus-visible:ring-1 focus-visible:outline-none
									{numericInvalid(k) ? 'border-destructive/60 focus-visible:ring-destructive/40' : 'border-input'}"
							/>
						{/if}
					</div>

					{#if hasDefault(k)}
						<Button
							variant="ghost"
							size="sm"
							class="h-8 shrink-0 cursor-pointer px-2.5 text-muted-foreground"
							onclick={() => restoreDefault(k)}
							title={i18n.t('admin.env.restore', { key: k.key })}
						>
							<Undo2 class="h-3.5 w-3.5" aria-hidden="true" />
						</Button>
					{/if}
				</div>
			{/each}
		</div>
	</div>
{:else}
	<div class="flex justify-center py-12">
		<Loader2 class="text-muted-foreground h-5 w-5 animate-spin" aria-hidden="true" />
	</div>
{/if}

<p class="text-muted-foreground text-xs">
	{i18n.t('admin.env.editHint')}
</p>

<style>
	input[type='number']::-webkit-outer-spin-button,
	input[type='number']::-webkit-inner-spin-button {
		-webkit-appearance: none;
		margin: 0;
	}

	input[type='number'] {
		-moz-appearance: textfield;
		appearance: textfield;
	}
</style>
