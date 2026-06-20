<script lang="ts">
	import MoonIcon from '@lucide/svelte/icons/moon';
	import SunIcon from '@lucide/svelte/icons/sun';

	import { Button } from '$lib/components/ui/button/index.js';
	import { appStore } from '$lib/stores/app-state.svelte';

	// Theme is owned by preferences (the single source of truth applied via
	// mode-watcher in +page). Toggle flips to the opposite of what's showing now.
	function toggle() {
		const isDark = document.documentElement.classList.contains('dark');

		appStore.updatePreferences({ theme: isDark ? 'light' : 'dark' });
	}
</script>

<Button onclick={toggle} variant="ghost" size="icon" class="relative">

	<SunIcon
		class="h-[1.2rem] w-[1.2rem] scale-100 rotate-0 transition-all! dark:scale-0 dark:-rotate-90"
	/>

	<MoonIcon
		class="absolute h-[1.2rem] w-[1.2rem] scale-0 rotate-90 transition-all! dark:scale-100 dark:rotate-0"
	/>
</Button>
