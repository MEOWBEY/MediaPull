<script lang="ts">
	import { onMount } from 'svelte';
	import { Toaster as Sonner, type ToasterProps as SonnerProps } from 'svelte-sonner';

	let { ...restProps }: SonnerProps = $props();

	// Theme is preference-driven and applied as a `.dark` class on <html>. Mirror
	// that class so toasts match light/dark from a single source of truth.
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
	expand
	visibleToasts={5}
	duration={3500}
	style="
		--normal-bg: var(--color-popover);
		--normal-text: var(--color-popover-foreground);
		--normal-border: var(--color-border);
		--border-radius: var(--radius);
		--success-bg: color-mix(in oklch, oklch(0.7 0.16 150) 22%, var(--color-popover));
		--success-text: oklch(0.72 0.16 150);
		--success-border: oklch(0.7 0.16 150 / 0.5);
		--error-bg: color-mix(in oklch, var(--color-destructive) 22%, var(--color-popover));
		--error-text: var(--color-destructive);
		--error-border: color-mix(in oklch, var(--color-destructive) 55%, transparent);
		--warning-bg: color-mix(in oklch, var(--color-warning) 22%, var(--color-popover));
		--warning-text: var(--color-warning);
		--warning-border: color-mix(in oklch, var(--color-warning) 55%, transparent);
		--info-bg: color-mix(in oklch, var(--color-signal) 20%, var(--color-popover));
		--info-text: var(--color-signal);
		--info-border: color-mix(in oklch, var(--color-signal) 50%, transparent);
	"
	toastOptions={{
		class: 'ds-toast',
		style:
			'box-shadow: var(--shadow-float); font-weight: 600; padding: 0.9rem 1rem;'
	}}
	{...restProps}
/>
