<script lang="ts">
	import { onMount } from 'svelte';
	import { Toaster as Sonner, type ToasterProps as SonnerProps } from 'svelte-sonner';

	let { ...restProps }: SonnerProps = $props();

	// Theme is preference-driven and applied as a `.dark` class on <html> (we no
	// longer use mode-watcher). Mirror that class so toasts match light/dark from a
	// single source of truth.
	let isDark = $state(false);

	onMount(() => {
		const el = document.documentElement;
		const sync = () => (isDark = el.classList.contains('dark'));

		sync();
		const observer = new MutationObserver(sync);

		observer.observe(el, { attributes: true, attributeFilter: ['class'] });

		return () => observer.disconnect();
	});
</script>

<Sonner
	theme={isDark ? 'dark' : 'light'}
	class="toaster group"
	position="bottom-right"
	richColors
	closeButton
	duration={3500}
	style="
		--normal-bg: color-mix(in oklch, var(--color-popover) 88%, transparent);
		--normal-text: var(--color-popover-foreground);
		--normal-border: color-mix(in oklch, var(--color-border) 80%, transparent);
		--border-radius: 1.3rem;
		--success-bg: color-mix(in oklch, var(--color-primary) 16%, var(--color-popover));
		--success-text: var(--color-primary);
		--success-border: color-mix(in oklch, var(--color-primary) 38%, transparent);
		--error-bg: color-mix(in oklch, var(--color-destructive) 16%, var(--color-popover));
		--error-text: var(--color-destructive);
		--error-border: color-mix(in oklch, var(--color-destructive) 38%, transparent);
		--warning-bg: color-mix(in oklch, var(--color-secondary) 18%, var(--color-popover));
		--warning-text: var(--color-secondary);
		--warning-border: color-mix(in oklch, var(--color-secondary) 40%, transparent);
		--info-bg: color-mix(in oklch, var(--color-accent) 60%, var(--color-popover));
		--info-text: var(--color-accent-foreground);
		--info-border: color-mix(in oklch, var(--color-border) 80%, transparent);
	"
	toastOptions={{
		class: 'ds-toast',
		style:
			'backdrop-filter: blur(14px) saturate(1.3); -webkit-backdrop-filter: blur(14px) saturate(1.3); box-shadow: var(--shadow-float); font-weight: 600; padding: 0.9rem 1rem;'
	}}
	{...restProps}
/>
