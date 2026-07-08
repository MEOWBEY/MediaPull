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
	// version that fits; 'L' error correction is the least redundant level --
	// fewer modules (a visibly less dense/"busy" grid) for the same URL, which
	// is what a phone camera actually needs for a clean on-screen scan (as
	// opposed to a printed code that might get scuffed/damaged, where 'M'+
	// redundancy earns its keep).
	const svg = $derived.by(() => {
		if (!url) {
			return '';
		}

		try {
			const qr = qrcode(0, 'L');

			qr.addData(url);
			qr.make();

			return qr.createSvgTag({ cellSize: 6, margin: 2, scalable: true });
		} catch {
			return '';
		}
	});
</script>

<Dialog.Root bind:open>
	<Dialog.Content class="max-w-sm" closeLabel={t('common.close')}>
		<Dialog.Header>
			<Dialog.Title>{t('qr.title')}</Dialog.Title>
			<Dialog.Description>{t('qr.desc')}</Dialog.Description>
		</Dialog.Header>

		{#if svg}
			<!-- White backing so dark modules stay scannable in dark mode. Sized up
			     from the old 240px box -- a bigger on-screen target with fewer
			     modules (see the 'L' error-correction note above) is what actually
			     makes a phone camera lock on quickly. -->
			<div class="mx-auto w-full max-w-72 rounded-xl bg-white p-4 [&_svg]:h-full [&_svg]:w-full">
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
