<script lang="ts">
	import Pause from '@lucide/svelte/icons/pause';
	import Play from '@lucide/svelte/icons/play';
	import Trash2 from '@lucide/svelte/icons/trash-2';
	import { onMount, onDestroy } from 'svelte';

	import { adminEventStream } from '$lib/admin.svelte';
	import { Button } from '$lib/components/ui/button';
	import { i18n } from '$lib/i18n/index.svelte';

	type LogEntry = {
		ts: string;
		level: string;
		name: string;
		message: string;
		ip: string;
		req: string;
	};

	const LEVELS = ['all', 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'] as const;
	const LEVEL_CLASS: Record<string, string> = {
		DEBUG: 'text-sky-400',
		INFO: 'text-muted-foreground',
		WARNING: 'text-amber-500',
		ERROR: 'text-destructive',
		CRITICAL: 'text-destructive font-bold'
	};

	let entries = $state<LogEntry[]>([]);
	let level = $state<(typeof LEVELS)[number]>('all');
	let paused = $state(false);
	let scroller = $state<HTMLDivElement | null>(null);
	let stuckToBottom = $state(true);

	let controller: AbortController | null = null;

	function shown(): LogEntry[] {
		if (level === 'all') {
			return entries;
		}

		return entries.filter((e) => levelOrder(e.level) <= levelOrder(level));
	}

	function levelOrder(l: string): number {
		return ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'].indexOf(l);
	}

	function fmtTime(iso: string): string {
		return iso.slice(11, 19);
	}

	async function connect() {
		controller = new AbortController();
		try {
			await adminEventStream(
				'/admin/logs/stream',
				(data) => {
					const { entries: incoming } = data as { entries?: LogEntry[] };

					if (incoming) {
						entries = incoming;
					}
				},
				controller.signal
			);
		} finally {
			controller = null;
		}
	}

	function togglePause() {
		paused = !paused;
		if (paused) {
			controller?.abort();
		} else {
			void connect();
		}
	}

	function clearScreen() {
		entries = [];
	}

	$effect(() => {
		const el = scroller;

		if (el && stuckToBottom) {
			el.scrollTop = el.scrollHeight;
		}
	});

	function onScroll() {
		const el = scroller;

		if (!el) {
			return;
		}
		stuckToBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
	}

	onMount(() => {
		// The SSE stream sends a full snapshot on connect — no separate fetch.
		void connect();
	});

	onDestroy(() => {
		controller?.abort();
	});
</script>

<div class="bg-card flex flex-col gap-0.5 overflow-hidden rounded-lg border">
	<div class="flex flex-wrap items-center gap-2 border-b p-2">
		<div
			class="border-border/70 flex max-w-full shrink-0 items-center overflow-x-auto rounded-md border"
			role="group"
			aria-label={i18n.t('admin.logs.levelFilter')}
		>
			{#each LEVELS as l, i (l)}
				<button
					type="button"
					onclick={() => (level = l)}
					class={[
						'shrink-0 border-border/70 font-mono text-xs h-8 cursor-pointer px-2.5 transition-colors',
						i > 0 && 'border-s',
						level === l
							? 'bg-signal/15 text-signal font-semibold'
							: 'hover:bg-muted text-muted-foreground hover:text-foreground'
					]}
				>
					{l === 'all' ? i18n.t('admin.logs.all') : l}
				</button>
			{/each}
		</div>
		<div class="text-muted-foreground ms-auto flex items-center gap-1">
			<span class="font-mono text-xs">{shown().length}</span>
			<Button
				variant="ghost"
				size="sm"
				class="h-8 cursor-pointer px-2"
				onclick={togglePause}
				title={paused ? i18n.t('admin.logs.resume') : i18n.t('admin.logs.pause')}
			>
				{#if paused}
					<Play class="h-4 w-4" aria-hidden="true" />
				{:else}
					<Pause class="h-4 w-4" aria-hidden="true" />
				{/if}
			</Button>
			<Button
				variant="ghost"
				size="sm"
				class="h-8 cursor-pointer px-2"
				onclick={clearScreen}
				title={i18n.t('admin.logs.clearTitle')}
			>
				<Trash2 class="h-4 w-4" aria-hidden="true" />
			</Button>
		</div>
	</div>

	<div
		bind:this={scroller}
		onscroll={onScroll}
		class="font-mono h-[26rem] overflow-y-auto p-2 text-xs leading-5"
		role="log"
		aria-live="polite"
	>
		{#if shown().length === 0}
			<p class="text-muted-foreground p-3">{i18n.t('admin.logs.empty')}</p>
		{/if}
		{#each shown() as entry (entry.ts + entry.req + entry.message)}
			<div
				class="hover:bg-muted/40 flex flex-wrap gap-x-2 py-0.5 min-[480px]:flex-nowrap"
			>
				<span class="shrink-0 text-muted-foreground/70">{fmtTime(entry.ts)}</span>
				<span class="w-16 shrink-0 {LEVEL_CLASS[entry.level] ?? 'text-muted-foreground'}">
					{entry.level}
				</span>
				<span class="min-w-0 basis-full flex-1 min-[480px]:basis-auto">
					{#if entry.name}
						<span class="text-signal" title={entry.name}>{entry.name.split('.').pop()}</span>&nbsp;
					{/if}
					<span class="text-muted-foreground/90 break-words">{entry.message}</span>
					{#if entry.ip !== '-'}
						<span class="text-muted-foreground/50"> [{entry.ip}]</span>
					{/if}
				</span>
			</div>
		{/each}
	</div>
</div>

<p class="text-muted-foreground text-xs">
	{i18n.t('admin.logs.bufferHint')}
</p>
