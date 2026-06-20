<script lang="ts">
	import Copy from '@lucide/svelte/icons/copy';
	import qrcode from 'qrcode-generator';

	import { Button } from '$lib/components/ui/button';
	import * as Dialog from '$lib/components/ui/dialog';
	import { i18n } from '$lib/i18n/index.svelte';

	const { t } = i18n;

	let {
		url = '',
		open = $bindable(false),
		onCopy
	}: { url?: string; open?: boolean; onCopy?: (url: string) => void } = $props();

	// Build a scalable SVG QR for the link. typeNumber 0 = auto-pick the smallest
	// version that fits; 'M' error correction tolerates a bit of camera noise.
	const svg = $derived.by(() => {
		if (!url) {return '';}

		try {
			const qr = qrcode(0, 'M');

			qr.addData(url);
			qr.make();

			return qr.createSvgTag({ cellSize: 6, margin: 2, scalable: true });
		} catch {
			return '';
		}
	});
</script>

<Dialog.Root bind:open>
	<Dialog.Content class="max-w-xs">
		<Dialog.Header>
			<Dialog.Title>{t('qr.title')}</Dialog.Title>
			<Dialog.Description>{t('qr.desc')}</Dialog.Description>
		</Dialog.Header>

		{#if svg}
			<!-- White backing so dark modules stay scannable in dark mode. -->
			<div
				class="mx-auto w-full max-w-60 rounded-xl bg-white p-3 [&_svg]:h-full [&_svg]:w-full"
			>
				<!-- eslint-disable-next-line svelte/no-at-html-tags -->
				{@html svg}
			</div>
			<!-- Clamp very long links to a few lines so the dialog doesn't sprawl;
			     the full URL is still available via the copy button below. -->
			<p dir="ltr" class="text-muted-foreground mt-3 line-clamp-3 break-all text-center text-xs">
				{url}
			</p>
			{#if onCopy}
				<Button variant="outline" size="sm" class="mt-3 w-full" onclick={() => onCopy?.(url)}>
					<Copy class="me-1.5 h-4 w-4" />{t('extract.copyUrl')}
				</Button>
			{/if}
		{:else}
			<p class="text-muted-foreground py-6 text-center text-sm">{t('qr.error')}</p>
		{/if}
	</Dialog.Content>
</Dialog.Root>
