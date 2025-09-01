<script lang="ts">
	import '../app.css';
	import { Button } from '$lib/components/ui/button';
	import Github from 'lucide-svelte/icons/github';
	import { ModeWatcher } from 'mode-watcher';
	import { ToggleMode } from '$lib/components/dark-mode/index';
	import { Toaster } from '$lib/components/ui/sonner/index.js';

	let { children } = $props();
	const MY_GITHUB = 'https://github.com/meowbey';
</script>

<Toaster />
<ModeWatcher />

<div class="bg-background flex min-h-screen flex-col">
	<!-- Main Navigation -->
	<header class="bg-background/80 border-b backdrop-blur-sm">
		<div class="container mx-auto px-4">
			<nav class="flex h-14 items-center justify-between" aria-label="Main navigation">
				<!-- Brand -->
				<div class="flex items-center space-x-3">
					<div class="flex items-center gap-2">
						<h1
							class="bg-gradient-to-r from-zinc-900 to-zinc-700 bg-clip-text text-lg font-semibold tracking-tight text-transparent dark:from-zinc-100 dark:to-zinc-300"
							id="site-title"
						>
							Video Extractor
						</h1>
					</div>
				</div>

				<!-- Navigation Actions -->
				<div class="flex items-center gap-1" role="group" aria-label="Theme and external links">
					<ToggleMode />
					<Button
						variant="ghost"
						size="sm"
						href={MY_GITHUB}
						target="_blank"
						rel="noopener noreferrer"
						class="flex hover:bg-zinc-100  dark:hover:bg-zinc-800"
						aria-label="Visit MEOWBEY GitHub profile (opens in new tab)"
					>
						<Github class="h-4 w-4" aria-hidden="true" />
						<span class="text-xs md:text-sm"> MEOWBEY</span>
					</Button>
				</div>
			</nav>
		</div>
	</header>

	<!-- Main Content Area -->
	<main
		id="main-content"
		class="flex min-h-screen w-full items-center justify-center bg-gray-100 dark:bg-zinc-800"
		tabindex="-1"
	>
		{@render children?.()}
	</main>
	<footer class="bg-background/80 border-t backdrop-blur-sm">
		<div
			class="text-muted-foreground container mx-auto flex h-14 items-center justify-between px-4 text-[0.75rem] sm:text-sm"
		>
			<div class="flex flex-wrap items-center gap-1">
				<span>Made by</span>
				<a
					href={MY_GITHUB}
					target="_blank"
					rel="noopener noreferrer"
					class="hover:text-foreground font-medium underline underline-offset-4"
				>
					MEOWBEY
				</a>
				<span>for educational purposes only.</span>
			</div>
			<div class="hidden text-right md:block">
				<span class="font-medium">&copy; {new Date().getFullYear()} Video Extractor</span>
			</div>
		</div>
	</footer>
</div>
