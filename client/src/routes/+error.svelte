<script lang="ts">
	import AlertTriangle from '@lucide/svelte/icons/alert-triangle';
	import Home from '@lucide/svelte/icons/home';

	import { page } from '$app/state';
	import { Button } from '$lib/components/ui/button';
	import { i18n } from '$lib/i18n/index.svelte';

	const { t } = i18n;
</script>

<svelte:head>
	<title>Error {page.status} | MediaPull</title>
	<meta name="robots" content="noindex, nofollow" />
</svelte:head>

<div class="min-h-screen">
	<div class="flex min-h-screen items-center justify-center px-4">
		<div class="w-full max-w-md">
			<div class="ds-glass rounded-lg p-8 text-center">
				<div class="mb-6 flex justify-center">
					<div class="bg-destructive/15 rounded-md p-4">
						<AlertTriangle class="text-destructive h-8 w-8" />
					</div>
				</div>

				{#if page.status === 404}
					<h1 class="font-heading text-foreground mb-2 text-4xl font-bold">404</h1>
					<h2 class="text-foreground mb-4 text-xl font-semibold">
						{t('errorPage.404Title')}
					</h2>
					<p class="text-muted-foreground mb-6">
						{t('errorPage.404Body')}
					</p>
				{:else if page.status === 500}
					<h1 class="font-heading text-foreground mb-2 text-4xl font-bold">500</h1>
					<h2 class="text-foreground mb-4 text-xl font-semibold">
						{t('errorPage.500Title')}
					</h2>
					<p class="text-muted-foreground mb-6">
						{t('errorPage.500Body')}
						{page.error?.message || t('errorPage.unknown')}
					</p>
				{:else}
					<h1 class="font-heading text-foreground mb-2 text-4xl font-bold">{page.status}</h1>
					<h2 class="text-foreground mb-4 text-xl font-semibold">
						{t('errorPage.genericTitle')}
					</h2>
					<p class="text-muted-foreground mb-6">
						{t('errorPage.genericBody')}
						{page.error?.message || t('errorPage.unknown')}
					</p>
				{/if}

				<Button href="/" class="gap-2">
					<Home class="h-4 w-4" />
					{t('errorPage.home')}
				</Button>
			</div>
		</div>
	</div>
</div>
