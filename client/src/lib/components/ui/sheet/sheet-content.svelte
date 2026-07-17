<script lang="ts" module>
	import { tv, type VariantProps } from 'tailwind-variants';

	export const sheetVariants = tv({
		base: 'bg-background data-[state=open]:animate-in data-[state=closed]:animate-out fixed z-50 flex flex-col gap-4 shadow-lg transition ease-[cubic-bezier(0.32,0.72,0,1)] data-[state=closed]:duration-300 data-[state=open]:duration-[400ms]',
		variants: {
			side: {
				top: 'data-[state=closed]:slide-out-to-top data-[state=open]:slide-in-from-top inset-x-0 top-0 h-auto border-b',
				bottom:
					'data-[state=closed]:slide-out-to-bottom data-[state=open]:slide-in-from-bottom inset-x-0 bottom-0 h-auto border-t',
				left: 'data-[state=closed]:slide-out-to-left data-[state=open]:slide-in-from-left inset-y-0 left-0 h-full w-3/4 border-r sm:max-w-sm',
				right:
					'data-[state=closed]:slide-out-to-right data-[state=open]:slide-in-from-right inset-y-0 right-0 h-full w-3/4 border-l sm:max-w-sm'
			}
		},
		defaultVariants: {
			side: 'right'
		}
	});

	export type Side = VariantProps<typeof sheetVariants>['side'];
</script>

<script lang="ts">
	import XIcon from '@lucide/svelte/icons/x';
	import { Dialog as SheetPrimitive } from 'bits-ui';

	import { cn, type WithoutChildrenOrChild } from '$lib/utils.js';

	import SheetOverlay from './sheet-overlay.svelte';

	import type { Snippet } from 'svelte';

	let {
		ref = $bindable(null),
		class: className,
		side = 'right',
		portalProps,
		children,
		closeLabel = 'Close',
		hideClose = false,
		...restProps
	}: WithoutChildrenOrChild<SheetPrimitive.ContentProps> & {
		portalProps?: SheetPrimitive.PortalProps;
		side?: Side;
		children: Snippet;
		/** Screen-reader label for the close button -- pass a translated
		 *  string; this component has no i18n access of its own. */
		closeLabel?: string;
		/** Hide the corner close (X) button. The sheet still closes via the
		 *  overlay tap / Esc -- some panels prefer a cleaner header without it. */
		hideClose?: boolean;
	} = $props();
</script>

<SheetPrimitive.Portal {...portalProps}>
	<SheetOverlay />
	<SheetPrimitive.Content
		bind:ref
		data-slot="sheet-content"
		class={cn(sheetVariants({ side }), className)}
		{...restProps}
	>
		{@render children?.()}
		{#if !hideClose}
			<SheetPrimitive.Close
				class="ring-offset-background focus-visible:ring-ring rounded-xs focus-visible:outline-hidden absolute end-4 top-4 opacity-70 transition-opacity hover:opacity-100 focus-visible:ring-2 focus-visible:ring-offset-2 disabled:pointer-events-none"
			>
				<XIcon class="size-4" />
				<span class="sr-only">{closeLabel}</span>
			</SheetPrimitive.Close>
		{/if}
	</SheetPrimitive.Content>
</SheetPrimitive.Portal>
