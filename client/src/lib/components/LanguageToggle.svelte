<script lang="ts">
	import Languages from '@lucide/svelte/icons/languages';

	import { Button } from '$lib/components/ui/button/index.js';
	import { i18n } from '$lib/i18n/index.svelte';
</script>

<!-- Taller on touch widths (thumb target), compact from sm up. Icon-only, to
     match the stroke weight and box of the other header controls; the language
     you'll switch TO lives in the tooltip and aria-label instead of a visible
     text label. No icon set ships an EN/FA mark (Material's translate glyph is
     文A, a Chinese character), so this stays the generic Lucide one. -->
<Button
	onclick={() => i18n.toggle()}
	variant="ghost"
	size="icon"
	class="h-10 w-10 sm:h-9 sm:w-9"
	title={i18n.locale === 'en' ? 'فارسی' : 'English'}
	aria-label="{i18n.t('nav.language')}: {i18n.locale === 'en' ? 'فارسی' : 'English'}"
>
	<Languages class="h-5 w-5" aria-hidden="true" />
</Button>
