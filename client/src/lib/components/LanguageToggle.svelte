<script lang="ts">
	import Languages from '@lucide/svelte/icons/languages';

	import { Button } from '$lib/components/ui/button/index.js';
	import { i18n } from '$lib/i18n/index.svelte';
</script>

<Button
	onclick={() => i18n.toggle()}
	variant="ghost"
	size="sm"
	class="gap-1.5"
	title={i18n.t('nav.language')}
	aria-label={i18n.t('nav.language')}
>
	<Languages class="h-4 w-4" aria-hidden="true" />
	<!-- Show the language you'll switch TO, so the action is obvious. -->
	<span class="text-xs font-semibold">{i18n.locale === 'en' ? 'فارسی' : 'EN'}</span>
</Button>
