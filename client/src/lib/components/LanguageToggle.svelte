<script lang="ts">
	import Languages from '@lucide/svelte/icons/languages';

	import { Button } from '$lib/components/ui/button/index.js';
	import { i18n } from '$lib/i18n/index.svelte';
</script>

<!-- Taller on touch widths (thumb target), compact from sm up. -->
<Button
	onclick={() => i18n.toggle()}
	variant="ghost"
	size="sm"
	class="h-10 gap-1.5 sm:h-8"
	title={i18n.t('nav.language')}
	aria-label={i18n.t('nav.language')}
>
	<Languages class="h-4 w-4" aria-hidden="true" />
	<!-- Show the language you'll switch TO, so the action is obvious. -->
	<span class="text-xs font-semibold">{i18n.locale === 'en' ? 'فارسی' : 'EN'}</span>
</Button>
