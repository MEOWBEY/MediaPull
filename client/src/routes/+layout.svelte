<script lang="ts">
	import Github from '@lucide/svelte/icons/code';
	import Settings from '@lucide/svelte/icons/settings';

	import { resolve } from '$app/paths';
	import { ToggleMode } from '$lib/components/dark-mode/index';
	import LanguageToggle from '$lib/components/LanguageToggle.svelte';
	import { Button } from '$lib/components/ui/button';
	import { Toaster } from '$lib/components/ui/sonner/index.js';
	import { i18n } from '$lib/i18n/index.svelte';
	import { ui } from '$lib/stores/ui.svelte';

	import '../app.css';

	let { children } = $props();
	const GITHUB_URL = 'https://github.com/meowbey';
	const GITHUB_USERNAME = 'MEOWBEY';

	// Sync lang/dir with locale (RTL for Farsi, correct screen-reader language).
	$effect(() => {
		if (typeof document === 'undefined') {
			return;
		}

		document.documentElement.lang = i18n.locale;
		document.documentElement.dir = i18n.dir;
	});
</script>

<Toaster />

<div class="ds-aurora" aria-hidden="true"></div>

<div class="flex min-h-screen flex-col">
	<!-- Header stays LTR so brand/actions don't flip under RTL page direction.
	     Not sticky — it scrolls away, since there's little in it worth keeping
	     pinned. A hairline bottom border sets the tool-like register. -->
	<header dir="ltr" class="ds-glass z-50 rounded-none border-x-0 border-t-0">
		<nav
			class="mx-auto flex h-14 w-full max-w-7xl items-center justify-between px-2 sm:px-4"
			aria-label="Main navigation"
		>
			<a href={resolve('/')} class="group flex shrink-0 items-center gap-2">
				<svg
					class="text-signal shrink-0"
					width="14"
					height="18"
					viewBox="0 0 14 18"
					fill="none"
					xmlns="http://www.w3.org/2000/svg"
					aria-hidden="true"
				>
					<rect x="0" y="3" width="14" height="3" rx="1.5" fill="currentColor" />
					<rect x="0" y="9" width="9" height="3" rx="1.5" fill="currentColor" />
					<rect x="0" y="15" width="6" height="3" rx="1.5" fill="currentColor" />
				</svg>
				<h1
					class="font-heading shrink-0 text-lg font-bold tracking-tight"
					id="site-title"
				>
					MediaPull
				</h1>
			</a>

			<div
				class="flex items-center gap-0.5 sm:gap-1"
				role="group"
				aria-label="Settings, theme and external links"
			>
				<LanguageToggle />
				<ToggleMode />
				<Button
					variant="ghost"
					size="icon"
					onclick={() => ui.openPreferences()}
					class="h-10 w-10 sm:h-9 sm:w-9"
					title={i18n.t('input.preferences')}
					aria-label={i18n.t('input.preferences')}
				>
					<Settings class="h-5 w-5" aria-hidden="true" />
				</Button>
				<Button
					variant="ghost"
					size="sm"
					href={GITHUB_URL}
					target="_blank"
					rel="noopener noreferrer"
					class="hidden sm:inline-flex"
					aria-label="Visit {GITHUB_URL} GitHub profile (opens in new tab)"
				>
					<Github class="h-4 w-4" aria-hidden="true" />
					<span class="hidden text-xs sm:inline">{GITHUB_USERNAME}</span>
				</Button>
			</div>
		</nav>
	</header>

	<main id="main-content" class="flex w-full flex-1 flex-col items-center" tabindex="-1">
		{@render children?.()}
	</main>

	<footer class="ds-glass mt-1 rounded-none border-x-0 border-b-0">
		<div
			class="text-muted-foreground mx-auto flex h-12 w-full max-w-7xl items-center justify-between gap-3 px-2 sm:px-4 font-mono text-xs"
		>
			<div class="flex min-w-0 items-center gap-1.5">
				<span class="text-signal shrink-0" aria-hidden="true">//</span>
				<span class="truncate" dir="auto">{i18n.t('nav.madeBy')}</span>
				<a
					href={GITHUB_URL}
					target="_blank"
					rel="noopener noreferrer"
					dir="ltr"
					class="text-signal shrink-0 underline-offset-2 hover:underline"
				>
					<bdi>{GITHUB_USERNAME}</bdi>
				</a>
			</div>
			<div class="hidden shrink-0 sm:block" dir="ltr">
				<span>© {new Date().getFullYear()} MediaPull</span>
			</div>
		</div>
	</footer>
</div>
