<script lang="ts">
	import '../app.css';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import Github from 'lucide-svelte/icons/github';
	import { ModeWatcher } from 'mode-watcher';
	import { ToggleMode } from '$lib/components/dark-mode/index';
	import { Toaster } from '$lib/components/ui/sonner/index.js';
	let { children } = $props();
</script>

<Toaster />
<ModeWatcher />

<div class="bg-background flex min-h-screen flex-col">
	<!-- Main Navigation -->
	<header
		class="bg-background/80 border-b backdrop-blur-sm"
	>
		<div class="container mx-auto px-4 sm:px-6">
			<nav class="flex h-12 items-center justify-between" aria-label="Main navigation">
				<!-- Brand -->
				<div class="flex items-center space-x-3">
					<div class="flex items-center gap-2">
						<h1
							class="bg-gradient-to-r from-zinc-900 to-zinc-700 bg-clip-text text-lg font-semibold tracking-tight text-transparent dark:from-zinc-100 dark:to-zinc-300"
							id="site-title"
						>
							DirectLinker
						</h1>
						<Badge
							variant="secondary"
							class="hidden text-xs sm:inline-flex"
							aria-label="Beta version"
						>
							Beta
						</Badge>
					</div>
				</div>

				<!-- Navigation Actions -->
				<div class="flex items-center gap-1" role="group" aria-label="Theme and external links">
					<ToggleMode />
					<Button
						variant="ghost"
						size="sm"
						href="https://github.com/meowbey"
						target="_blank"
						rel="noopener noreferrer"
						class="flex hover:bg-zinc-100 dark:hover:bg-zinc-800"
						aria-label="Visit MEOWBEY GitHub profile (opens in new tab)"
					>
						<Github class="h-4 w-4" aria-hidden="true" />

						MEOWBEY
					</Button>
				</div>
			</nav>
		</div>
	</header>

	<!-- Main Content Area -->
	<main
		id="main-content"
		class="flex min-h-screen w-full items-center justify-center bg-gray-100 dark:bg-zinc-900"
		tabindex="-1"
	>
		{@render children?.()}
	</main>

</div>
