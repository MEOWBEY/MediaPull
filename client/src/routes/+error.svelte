<script lang="ts">
	import AlertTriangle from '@lucide/svelte/icons/alert-triangle';
	import Home from '@lucide/svelte/icons/home';

	import { page } from '$app/state';
	import { Button } from '$lib/components/ui/button';
	import { i18n } from '$lib/i18n/index.svelte';

	const { t } = i18n;
</script>

<svelte:head>
	<title>Error {page.status} | DirectStream</title>
	<meta name="robots" content="noindex, nofollow" />
</svelte:head>

<div class="min-h-screen">
	<div class="flex min-h-screen items-center justify-center px-4">
		<div class="w-full max-w-md">
			
			<!-- Error Card -->
			<div class="ds-glass rounded-2xl border-0 p-8 text-center shadow-glow">
				<div class="mb-6 flex justify-center">
					<div class="rounded-2xl bg-red-500/15 p-4">
						<AlertTriangle class="h-8 w-8 text-red-500" />
					</div>
				</div>

				{#if page.status === 404}
					<h1 class="mb-2 text-4xl font-bold text-zinc-900 dark:text-zinc-100">404</h1>
					<h2 class="mb-4 text-xl font-semibold text-zinc-900 dark:text-zinc-100">
						{t('errorPage.404Title')}
					</h2>
					<p class="mb-6 text-zinc-600 dark:text-zinc-400">
						{t('errorPage.404Body')}
					</p>
				{:else if page.status === 500}
					<h1 class="mb-2 text-4xl font-bold text-zinc-900 dark:text-zinc-100">500</h1>
					<h2 class="mb-4 text-xl font-semibold text-zinc-900 dark:text-zinc-100">
						{t('errorPage.500Title')}
					</h2>
					<p class="mb-6 text-zinc-600 dark:text-zinc-400">
						{t('errorPage.500Body')}
						{page.error?.message || t('errorPage.unknown')}
					</p>
				{:else}
					<h1 class="mb-2 text-4xl font-bold text-zinc-900 dark:text-zinc-100">{page.status}</h1>
					<h2 class="mb-4 text-xl font-semibold text-zinc-900 dark:text-zinc-100">
						{t('errorPage.genericTitle')}
					</h2>
					<p class="mb-6 text-zinc-600 dark:text-zinc-400">
						{t('errorPage.genericBody')}
						{page.error?.message || t('errorPage.unknown')}
					</p>
				{/if}

				<Button href="/" class="bg-primary text-primary-foreground hover:bg-primary/90 gap-2">
					<Home class="h-4 w-4" />
					{t('errorPage.home')}
				</Button>
			</div>
		</div>
	</div>
</div>
