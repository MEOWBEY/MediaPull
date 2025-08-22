<script lang="ts">
	import { page } from '$app/state';
	import AlertTriangle from 'lucide-svelte/icons/alert-triangle';
	import Home from 'lucide-svelte/icons/home';
	import { Button } from '$lib/components/ui/button';
</script>

<svelte:head>
	<title>Error {page.status} - Video Downloader</title>
	<meta name="robots" content="noindex, nofollow" />
</svelte:head>

<div class="min-h-screen">
	<div class="flex min-h-screen items-center justify-center px-4">
		<div class="w-full max-w-md">
			<!-- Error Card -->
			<div
				class="rounded-lg border border-gray-200 bg-white p-8 text-center dark:border-zinc-800 dark:bg-zinc-900"
			>
				<div class="mb-6 flex justify-center">
					<div class="rounded-lg bg-red-100 p-4 dark:bg-red-900/20">
						<AlertTriangle class="h-8 w-8 text-red-600 dark:text-red-400" />
					</div>
				</div>

				{#if page.status === 404}
					<h1 class="mb-2 text-4xl font-bold text-zinc-900 dark:text-zinc-100">404</h1>
					<h2 class="mb-4 text-xl font-semibold text-zinc-900 dark:text-zinc-100">
						Page Not Found
					</h2>
					<p class="mb-6 text-zinc-600 dark:text-zinc-400">
						Oops! The page you're looking for doesn't exist.
					</p>
				{:else if page.status === 500}
					<h1 class="mb-2 text-4xl font-bold text-zinc-900 dark:text-zinc-100">500</h1>
					<h2 class="mb-4 text-xl font-semibold text-zinc-900 dark:text-zinc-100">Server Error</h2>
					<p class="mb-6 text-zinc-600 dark:text-zinc-400">
						Sorry! Something went wrong on our end: {page.error?.message || 'Unknown error'}
					</p>
				{:else}
					<h1 class="mb-2 text-4xl font-bold text-zinc-900 dark:text-zinc-100">{page.status}</h1>
					<h2 class="mb-4 text-xl font-semibold text-zinc-900 dark:text-zinc-100">
						Error Occurred
					</h2>
					<p class="mb-6 text-zinc-600 dark:text-zinc-400">
						An error has occurred: {page.error?.message || 'Unknown error'}
					</p>
				{/if}

				<Button href="/" class="gap-2">
					<Home class="h-4 w-4" />
					Back to Home
				</Button>
			</div>
		</div>
	</div>
</div>
