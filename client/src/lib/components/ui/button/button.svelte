<script lang="ts" module>
	import { type VariantProps, tv } from 'tailwind-variants';

	import { cn, type WithElementRef } from '$lib/utils.js';

	import type { HTMLAnchorAttributes, HTMLButtonAttributes } from 'svelte/elements';

	export const buttonVariants = tv({
		base: "cursor-pointer focus-visible:border-ring focus-visible:ring-ring/50 aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-full text-sm font-medium outline-none transition-colors duration-200 ease-out focus-visible:ring-[3px] disabled:pointer-events-none disabled:opacity-50 aria-disabled:pointer-events-none aria-disabled:opacity-50 [&_svg:not([class*='size-'])]:size-4 [&_svg]:pointer-events-none [&_svg]:shrink-0",
		variants: {
			variant: {
				// Moss bg / pale-mist text, soft colored shadow that deepens on hover.
				default:
					'bg-primary text-primary-foreground shadow-soft hover:bg-primary/90 hover:shadow-float',
				destructive:
					'bg-destructive hover:bg-destructive/90 shadow-soft focus-visible:ring-destructive/20 dark:focus-visible:ring-destructive/40 dark:bg-destructive/60 text-white',
				// 2px terracotta border, transparent bg, terracotta text.
				outline:
					'border-2 border-secondary text-secondary bg-transparent hover:bg-secondary/10 dark:bg-transparent dark:border-secondary dark:hover:bg-secondary/15',
				secondary:
					'bg-secondary text-secondary-foreground shadow-soft hover:bg-secondary/90 hover:shadow-float',
				ghost: 'hover:bg-accent hover:text-accent-foreground dark:hover:bg-accent/50',
				link: 'text-primary underline-offset-4 hover:underline'
			},
			size: {
				// Generous, comfortable defaults for the organic system.
				default: 'h-12 px-8 py-2 has-[>svg]:px-6',
				sm: 'h-9 gap-1.5 px-5 has-[>svg]:px-3.5',
				lg: 'h-12 px-10 has-[>svg]:px-8',
				icon: 'size-9'
			}
		},
		defaultVariants: {
			variant: 'default',
			size: 'default'
		}
	});

	export type ButtonVariant = VariantProps<typeof buttonVariants>['variant'];
	export type ButtonSize = VariantProps<typeof buttonVariants>['size'];

	export type ButtonProps = WithElementRef<HTMLButtonAttributes> &
		WithElementRef<HTMLAnchorAttributes> & {
			variant?: ButtonVariant;
			size?: ButtonSize;
		};
</script>

<script lang="ts">
	let {
		class: className,
		variant = 'default',
		size = 'default',
		ref = $bindable(null),
		href = undefined,
		type = 'button',
		disabled,
		children,
		...restProps
	}: ButtonProps = $props();
</script>

{#if href}
	<a
		bind:this={ref}
		data-slot="button"
		class={cn(buttonVariants({ variant, size }), className)}
		href={disabled ? undefined : href}
		aria-disabled={disabled}
		role={disabled ? 'link' : undefined}
		tabindex={disabled ? -1 : undefined}
		{...restProps}
	>
		{@render children?.()}
	</a>
{:else}
	<button
		bind:this={ref}
		data-slot="button"
		class={cn(buttonVariants({ variant, size }), className)}
		{type}
		{disabled}
		{...restProps}
	>
		{@render children?.()}
	</button>
{/if}
