<script lang="ts">
	import Github from '@lucide/svelte/icons/code';
	import Zap from '@lucide/svelte/icons/zap';

	import { resolve } from '$app/paths';
	import { ToggleMode } from '$lib/components/dark-mode/index';
	import LanguageToggle from '$lib/components/LanguageToggle.svelte';
	import { Button } from '$lib/components/ui/button';
	import { Toaster } from '$lib/components/ui/sonner/index.js';
	import { i18n } from '$lib/i18n/index.svelte';

	import '../app.css';

	let { children } = $props();
	const MY_GITHUB = 'https://github.com/meowbey';

	// Keep the document direction + language in sync with the active locale so
	// the whole app mirrors for Farsi (RTL) and screen readers announce correctly.
	$effect(() => {
		if (typeof document === 'undefined') {return;}

		document.documentElement.lang = i18n.locale;
		document.documentElement.dir = i18n.dir;
	});
</script>

<Toaster />

<div class="ds-aurora" aria-hidden="true"></div>

<div class="flex min-h-screen flex-col">
	<!-- Main Navigation — kept LTR in every locale so the brand/actions layout
	     stays fixed even when the page mirrors to RTL for Farsi. -->
	<!-- Floating pill, NOT sticky — it scrolls away with the page so it's out of the
	     way once you scroll down. -->
	<header dir="ltr" class="z-50 px-4 pt-4">
		<div class="ds-glass shadow-soft container mx-auto rounded-full px-2">
			<nav class="flex h-14 items-center justify-between ps-3 pe-1" aria-label="Main navigation">
				<!-- Brand -->
				<a href={resolve('/')} class="group flex items-center gap-2">
					<span
						class="bg-primary shadow-soft flex h-9 w-9 items-center justify-center rounded-2xl transition-transform group-hover:scale-105"
					>
						<Zap class="h-5 w-5 text-white" aria-hidden="true" />
					</span>
					<h1
						class="ds-gradient-text font-heading text-base font-extrabold tracking-tight sm:text-xl"
						id="site-title"
					>
						Pullbox
					</h1>
				</a>

				<!-- Navigation Actions -->
				<div
						class="flex items-center gap-0.5 sm:gap-1"
						role="group"
						aria-label="Theme and external links"
					>
					<LanguageToggle />
					<ToggleMode />
					<Button
						variant="ghost"
						size="sm"
						href={MY_GITHUB}
						target="_blank"
						rel="noopener noreferrer"
						class="hidden rounded-full sm:inline-flex"
						aria-label="Visit MEOWBEY GitHub profile (opens in new tab)"
					>
						<Github class="h-4 w-4" aria-hidden="true" />
						<span class="hidden text-xs sm:inline md:text-sm">MEOWBEY</span>
					</Button>
				</div>
			</nav>
		</div>
	</header>

	<!-- Main Content Area -->
	<main id="main-content" class="flex w-full flex-1 flex-col items-center" tabindex="-1">
		{@render children?.()}
	</main>

	<!-- Footer — also pinned LTR to match the header. -->
	<footer dir="ltr" class="ds-glass border-x-0 border-b-0">
		<div
			class="text-muted-foreground container mx-auto flex h-14 items-center justify-between px-4 text-[0.75rem] sm:text-sm"
		>
			<div class="flex flex-wrap items-center gap-1">
				<span>{i18n.t('nav.madeBy')}</span>
				<a
					href={MY_GITHUB}
					target="_blank"
					rel="noopener noreferrer"
					class="ds-gradient-text font-semibold underline underline-offset-2"
				>
					MEOWBEY
				</a>
			</div>
			<div class="hidden text-right md:block">
				<span class="font-medium">{new Date().getFullYear()} Pullbox</span>
			</div>
		</div>
	</footer>
</div>
