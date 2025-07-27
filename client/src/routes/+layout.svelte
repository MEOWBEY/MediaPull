<script lang="ts">
	import '../app.css';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import Github from 'lucide-svelte/icons/github';
	import { ModeWatcher } from 'mode-watcher';
	import { ToggleMode } from '$lib/components/dark-mode/index';
	let { children } = $props();
</script>

<ModeWatcher />

<div class="bg-background flex min-h-screen flex-col">
	<!-- Skip to main content for screen readers -->
	<a 
		href="#main-content" 
		class="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-[100] focus:rounded focus:bg-blue-600 focus:px-3 focus:py-2 focus:text-white focus:outline-none"
	>
		Skip to main content
	</a>

	<!-- Main Navigation -->
	<header
		class="bg-background/80 fixed top-0 right-0 left-0 z-50 border-b backdrop-blur-sm transition-transform duration-300"
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
					</Button>
				</div>
			</nav>
		</div>
	</header>

	<!-- Main Content Area -->
	<main
		id="main-content"
		class="flex min-h-screen w-full items-center justify-center bg-gray-100 pt-16 dark:bg-zinc-900"
		tabindex="-1"
	>
		{@render children?.()}
	</main>

	<!-- Site Footer -->
	<footer 
		class="bg-background/60 border-t backdrop-blur-sm" 
		aria-label="Site footer"
	>
		<div class="container mx-auto px-4 py-6 sm:px-6">
			<div class="flex flex-col items-center justify-between gap-4 sm:flex-row">
				<div class="flex items-center space-x-2">
					<span class="text-muted-foreground text-sm font-medium">DirectLinker</span>
				</div>

				<div class="text-muted-foreground flex items-center text-xs">
					<a
						href="https://github.com/meowbey"
						target="_blank"
						rel="noopener noreferrer"
						class="hover:text-foreground font-medium underline transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
						aria-label="Visit MEOWBEY GitHub profile (opens in new tab)"
					>
						Made by MEOWBEY
					</a>
				</div>
			</div>
		</div>
	</footer>
</div>
