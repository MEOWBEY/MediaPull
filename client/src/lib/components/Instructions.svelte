<script lang="ts">
	import { Badge } from '$lib/components/ui/badge';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import FileText from 'lucide-svelte/icons/file-text';
	import { videoStore } from '$lib/stores/app-state.svelte';

	let preferences = $derived(videoStore.preferences);
</script>

<Card class="border shadow-sm {preferences.highContrast ? 'border-2' : ''}">
	<CardHeader class={preferences.compactMode ? 'py-3' : ''}>
		<CardTitle class="flex items-center gap-2 {preferences.compactMode ? 'text-base' : 'text-lg'}">
			<FileText class="h-5 w-5 text-gray-600" />
			How to Use
		</CardTitle>
	</CardHeader>
	<CardContent>
		<div class="grid {preferences.compactMode ? 'gap-2' : 'gap-4'} sm:grid-cols-2">
			<div class={preferences.compactMode ? 'space-y-2' : 'space-y-3'}>
				<div class="flex items-start gap-2">
					<Badge variant="outline" class="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center text-xs">1</Badge>
					<div>
						<h4 class="mb-1 font-medium {preferences.compactMode ? 'text-sm' : ''}">
							Extract Formats
						</h4>
						<p class="text-gray-600 dark:text-gray-400 {preferences.compactMode ? 'text-xs' : 'text-sm'}">
							Enter a video URL and click "Extract Formats" to see available options.
						</p>
					</div>
				</div>
				<div class="flex items-start gap-2">
					<Badge variant="outline" class="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center text-xs">2</Badge>
					<div>
						<h4 class="mb-1 font-medium {preferences.compactMode ? 'text-sm' : ''}">
							Choose Quality
						</h4>
						<p class="text-gray-600 dark:text-gray-400 {preferences.compactMode ? 'text-xs' : 'text-sm'}">
							Select your preferred format and quality from the list.
						</p>
					</div>
				</div>
				<div class="flex items-start gap-2">
					<Badge variant="outline" class="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center text-xs">3</Badge>
					<div>
						<h4 class="mb-1 font-medium {preferences.compactMode ? 'text-sm' : ''}">
							Process & Download
						</h4>
						<p class="text-gray-600 dark:text-gray-400 {preferences.compactMode ? 'text-xs' : 'text-sm'}">
							Process formats or use "Process" for quick downloads.
						</p>
					</div>
				</div>
			</div>
			<div class={preferences.compactMode ? 'space-y-2' : 'space-y-3'}>
				<div class="flex items-start gap-2">
					<Badge variant="outline" class="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center text-xs">4</Badge>
					<div>
						<h4 class="mb-1 font-medium {preferences.compactMode ? 'text-sm' : ''}">Proxy Mode</h4>
						<p class="text-gray-600 dark:text-gray-400 {preferences.compactMode ? 'text-xs' : 'text-sm'}">
							Toggle proxy to use original URLs instead of processed ones.
						</p>
					</div>
				</div>
				<div class="flex items-start gap-2">
					<Badge variant="outline" class="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center text-xs">5</Badge>
					<div>
						<h4 class="mb-1 font-medium {preferences.compactMode ? 'text-sm' : ''}">
							Shortcuts
						</h4>
						<p class="text-gray-600 dark:text-gray-400 {preferences.compactMode ? 'text-xs' : 'text-sm'}">
							{#if preferences.keyboardShortcuts}
								Use Ctrl+Enter to extract, Escape to cancel, Ctrl+K to search.
							{:else}
								Keyboard shortcuts are disabled in preferences.
							{/if}
						</p>
					</div>
				</div>
				<div class="flex items-start gap-2">
					<Badge variant="outline" class="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center text-xs">6</Badge>
					<div>
						<h4 class="mb-1 font-medium {preferences.compactMode ? 'text-sm' : ''}">
							Video Player
						</h4>
						<p class="text-gray-600 dark:text-gray-400 {preferences.compactMode ? 'text-xs' : 'text-sm'}">
							Built-in player supports HLS and standard formats with quality switching.
						</p>
					</div>
				</div>
			</div>
		</div>
	</CardContent>
</Card>