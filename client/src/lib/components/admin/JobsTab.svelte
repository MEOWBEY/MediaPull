<script lang="ts">
	import X from '@lucide/svelte/icons/x';
	import { onMount, onDestroy } from 'svelte';

	import { adminGet, adminPost } from '$lib/admin.svelte';
	import { Button } from '$lib/components/ui/button';
	import { i18n } from '$lib/i18n/index.svelte';

	type Job = {
		type: string;
		id: string;
		status: string;
		progress: number;
		stepLabel: string | null;
		detail: string | null;
		error: string | null;
		ageSeconds: number;
		ip: string;
	};

	let jobs = $state<Job[]>([]);
	let loaded = $state(false);
	let cancelling = $state('');

	let timer: ReturnType<typeof setInterval> | null = null;

	async function refresh() {
		try {
			const r = await adminGet<{ jobs: Job[] }>('/admin/jobs');

			jobs = r.jobs.sort((a, b) => b.ageSeconds - a.ageSeconds);
			loaded = true;
		} catch {
			/* session expired → the page gate handles logout on next interaction */
		}
	}

	async function cancel(job: Job) {
		cancelling = job.id;
		try {
			await adminPost(`/admin/jobs/${job.type}/${job.id}/cancel`);
		} finally {
			cancelling = '';
			void refresh();
		}
	}

	function fmtAge(secs: number): string {
		if (secs < 60) {
			return `${secs}s`;
		}
		if (secs < 3600) {
			return `${Math.floor(secs / 60)}m`;
		}

		return `${Math.floor(secs / 3600)}h${Math.floor((secs % 3600) / 60)}m`;
	}

	function progressBar(job: Job): string {
		const pct = Math.max(0, Math.min(100, Math.round(job.progress)));

		return `linear-gradient(90deg, var(--primary) ${pct}%, var(--border) ${pct}%)`;
	}

	onMount(() => {
		void refresh();
		timer = setInterval(() => void refresh(), 3000);
	});

	onDestroy(() => {
		if (timer) {
			clearInterval(timer);
		}
	});
</script>

<div class="bg-card overflow-hidden rounded-lg border">
	<div class="flex items-center justify-between border-b p-3">
		<h2 class="text-sm font-semibold">{i18n.t('admin.jobs.title')}</h2>
		<span class="text-muted-foreground font-mono text-xs">
			{i18n.t('admin.jobs.total', { n: loaded ? jobs.length : '…' })}&nbsp;·&nbsp;
			{i18n.t('admin.jobs.active', {
				n: jobs.filter((j) => j.status === 'queued' || j.status === 'running').length
			})}
		</span>
	</div>

	{#if !loaded || jobs.length === 0}
		<p class="text-muted-foreground p-6 text-sm">
			{loaded ? i18n.t('admin.jobs.empty') : i18n.t('admin.jobs.loading')}
		</p>
	{:else}
		<div class="divide-border/70 divide-y">
			{#each jobs as job (job.type + job.id)}
				<div class="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2.5">
					<span class="w-24 shrink-0 font-mono text-xs text-muted-foreground">{job.type}</span>
					<span class="text-sm font-medium">
						{job.status}
						{#if job.stepLabel}
							<span class="text-muted-foreground font-normal"> — {job.stepLabel}</span>
						{/if}
					</span>
					<span class="text-muted-foreground font-mono text-xs">
						{fmtAge(job.ageSeconds)} · {job.ip}
					</span>
					<span class="ms-auto flex items-center gap-2">
						{#if job.status === 'queued' || job.status === 'running'}
							<span
								class="h-1.5 w-24 overflow-hidden rounded-full"
								style:background={progressBar(job)}
								role="progressbar"
								aria-valuenow={Math.round(job.progress)}
								aria-valuemin="0"
								aria-valuemax="100"
							></span>
							<Button
								variant="outline"
								size="sm"
								class="h-8 cursor-pointer px-2"
								onclick={() => void cancel(job)}
								disabled={cancelling === job.id}
								title={i18n.t('admin.jobs.cancelTitle')}
							>
								<X class="h-3.5 w-3.5" aria-hidden="true" />
							</Button>
						{/if}
					</span>
					{#if job.error}
						<p class="text-destructive w-full truncate font-mono text-xs" title={job.error}>
							{job.detail ?? job.error}
						</p>
					{/if}
				</div>
			{/each}
		</div>
	{/if}
</div>

<p class="text-muted-foreground text-xs">
	{i18n.t('admin.jobs.bufferHint')}
</p>
