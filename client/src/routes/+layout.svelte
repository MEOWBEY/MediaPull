<script lang="ts">
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
				aria-label="Project link, language, theme and settings"
			>
				<!-- Order runs peripheral → primary. GitHub is the only control that
				     leaves the app, so it sits furthest from the edge; Settings is the
				     most-used, so it takes the privileged last slot. -->
				<Button
					variant="ghost"
					size="icon"
					href={GITHUB_URL}
					target="_blank"
					rel="noopener noreferrer"
					class="h-10 w-10 sm:h-9 sm:w-9"
					title="GitHub"
					aria-label="Visit {GITHUB_USERNAME} on GitHub (opens in new tab)"
				>
					<!-- GitHub's mark isn't in Lucide, so it's inlined from the official
					     Octicons set. Sized under the stroke icons beside it: a solid glyph
					     fills its whole box, so it reads heavier at equal dimensions. -->
					<svg
						class="size-4 sm:size-4.5"
						viewBox="0 0 16 16"
						fill="currentColor"
						xmlns="http://www.w3.org/2000/svg"
						aria-hidden="true"
					>
						<path
							d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.07-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A7.995 7.995 0 0 0 16 8c0-4.42-3.58-8-8-8Z"
						/>
					</svg>
				</Button>
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
