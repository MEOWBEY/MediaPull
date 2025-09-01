<script lang="ts">
	import { Badge } from '$lib/components/ui/badge';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import FileText from 'lucide-svelte/icons/file-text';
	import Zap from 'lucide-svelte/icons/zap';
	import Keyboard from 'lucide-svelte/icons/keyboard';
	let { preferences } = $props();
</script>

<div class="space-y-6">
	<!-- About This Tool Card -->
	<Card class=" ">
		<CardHeader class={preferences.enableCompact ? 'py-3' : ''}>
			<CardTitle
				class="flex items-center gap-2 {preferences.enableCompact ? 'text-base' : 'text-lg'}"
			>
				<FileText class="h-5 w-5 text-gray-600" />
				About This Tool
			</CardTitle>
			<p
				class="mb-4 text-gray-600 dark:text-gray-400 {preferences.enableCompact
					? 'text-xs'
					: 'text-sm'}"
			>
				Learn how to extract and accelerate video content with our advanced tool.
			</p>
		</CardHeader>
		<CardContent>
			<!-- Feature Overview -->
			<div class="grid {preferences.enableCompact ? 'gap-3' : 'gap-4'} sm:grid-cols-2">
				<div class={preferences.enableCompact ? 'space-y-2' : 'space-y-3'}>
					<div class="flex items-start gap-2">
						<div>
							<h4 class="mb-1 font-medium {preferences.enableCompact ? 'text-sm' : ''}">
								Video Extraction
							</h4>
							<p
								class="text-gray-600 dark:text-gray-400 {preferences.enableCompact
									? 'text-xs'
									: 'text-sm'}"
							>
								Paste any webpage URL containing videos. Our extraction engine automatically
								discovers all available video streams and formats.
							</p>
							<div class="mt-2 flex flex-wrap gap-1">
								<Badge variant="secondary" class="text-xs">MP4</Badge>
								<Badge variant="secondary" class="text-xs">HLS</Badge>
								<Badge variant="secondary" class="text-xs">WebM</Badge>
							</div>
						</div>
					</div>
				</div>

				<div class={preferences.enableCompact ? 'space-y-2' : 'space-y-3'}>
					<div class="flex items-start gap-2">
						<div>
							<h4 class="mb-1 font-medium {preferences.enableCompact ? 'text-sm' : ''}">
								Video Acceleration
							</h4>
							<p
								class="text-gray-600 dark:text-gray-400 {preferences.enableCompact
									? 'text-xs'
									: 'text-sm'}"
							>
								Boost streaming speeds and bypass restrictions using high-performance proxy servers.
								Perfect for slow connections.
							</p>
							<div class="mt-2 flex flex-wrap gap-1">
								<Badge variant="secondary" class="text-xs">Fast Servers</Badge>
								<Badge variant="secondary" class="text-xs">Geo Unblocking</Badge>
							</div>
						</div>
					</div>
				</div>
			</div>
		</CardContent>
	</Card>

	<!-- How It Works Card -->
	<Card class=" ">
		<CardHeader class={preferences.enableCompact ? 'py-3' : ''}>
			<CardTitle
				class="flex items-center gap-2 {preferences.enableCompact ? 'text-base' : 'text-lg'}"
			>
				<Zap class="h-5 w-5 text-gray-600" />
				How It Works
			</CardTitle>
			<p
				class="mb-4 text-gray-600 dark:text-gray-400 {preferences.enableCompact
					? 'text-xs'
					: 'text-sm'}"
			>
				Get started with video extraction and acceleration in simple steps.
			</p>
		</CardHeader>
		<CardContent>
			<div class="grid {preferences.enableCompact ? 'gap-2' : 'gap-4'} sm:grid-cols-2">
				<div class={preferences.enableCompact ? 'space-y-2' : 'space-y-3'}>
					<div class="flex items-start gap-2">
						<div>
							<h4 class="mb-1 font-medium {preferences.enableCompact ? 'text-sm' : ''}">
								Paste Video URL
							</h4>
							<p
								class="text-gray-600 dark:text-gray-400 {preferences.enableCompact
									? 'text-xs'
									: 'text-sm'}"
							>
								Copy and paste any webpage URL containing videos. We support major platforms.
							</p>
						</div>
					</div>

					<div class="flex items-start gap-2">
						<div>
							<h4 class="mb-1 font-medium {preferences.enableCompact ? 'text-sm' : ''}">
								Extract & Analyze
							</h4>
							<p
								class="text-gray-600 dark:text-gray-400 {preferences.enableCompact
									? 'text-xs'
									: 'text-sm'}"
							>
								Click extract to scan the page and identify available video streams automatically.
							</p>
						</div>
					</div>

					<div class="flex items-start gap-2">
						<div>
							<h4 class="mb-1 font-medium {preferences.enableCompact ? 'text-sm' : ''}">
								Choose Quality
							</h4>
							<p
								class="text-gray-600 dark:text-gray-400 {preferences.enableCompact
									? 'text-xs'
									: 'text-sm'}"
							>
								Select your preferred video quality and format from the available options.
							</p>
						</div>
					</div>
				</div>

				<div class={preferences.enableCompact ? 'space-y-2' : 'space-y-3'}>
					<div class="flex items-start gap-2">
						<div>
							<h4 class="mb-1 font-medium {preferences.enableCompact ? 'text-sm' : ''}">
								Enable Acceleration
							</h4>
							<p
								class="text-gray-600 dark:text-gray-400 {preferences.enableCompact
									? 'text-xs'
									: 'text-sm'}"
							>
								Toggle proxy mode for faster streaming and to bypass geographical restrictions.
							</p>
						</div>
					</div>

					<div class="flex items-start gap-2">
						<div>
							<h4 class="mb-1 font-medium {preferences.enableCompact ? 'text-sm' : ''}">
								Preview or Download
							</h4>
							<p
								class="text-gray-600 dark:text-gray-400 {preferences.enableCompact
									? 'text-xs'
									: 'text-sm'}"
							>
								Use the built-in player to preview or directly download the video file.
							</p>
						</div>
					</div>

					<div class="flex items-start gap-2">
						<div>
							<h4 class="mb-1 font-medium {preferences.enableCompact ? 'text-sm' : ''}">
								Enjoy Fast Streaming
							</h4>
							<p
								class="text-gray-600 dark:text-gray-400 {preferences.enableCompact
									? 'text-xs'
									: 'text-sm'}"
							>
								Experience improved speeds and unblocked access with our optimized network.
							</p>
						</div>
					</div>
				</div>
			</div>
		</CardContent>
	</Card>

	<!-- Key Features Card -->
	<Card class=" ">
		<CardHeader class={preferences.enableCompact ? 'py-3' : ''}>
			<CardTitle
				class="flex items-center gap-2 {preferences.enableCompact ? 'text-base' : 'text-lg'}"
			>
				<Keyboard class="h-5 w-5 text-gray-600" />
				Key Features
			</CardTitle>
			<p
				class="mb-4 text-gray-600 dark:text-gray-400 {preferences.enableCompact
					? 'text-xs'
					: 'text-sm'}"
			>
				Advanced capabilities for the best video isOVCProxyRunning experience.
			</p>
		</CardHeader>
		<CardContent>
			<div
				class="grid {preferences.enableCompact ? 'gap-2' : 'gap-4'} sm:grid-cols-2 lg:grid-cols-2"
			>
				<div class="flex items-start gap-2">
					<div>
						<h4 class="mb-1 font-medium {preferences.enableCompact ? 'text-sm' : ''}">
							Built-in Player
						</h4>
						<p
							class="text-gray-600 dark:text-gray-400 {preferences.enableCompact
								? 'text-xs'
								: 'text-sm'}"
						>
							Preview videos with HLS streaming, quality switching, and full-screen playback.
						</p>
					</div>
				</div>

				<div class="flex items-start gap-2">
					<div>
						<h4 class="mb-1 font-medium {preferences.enableCompact ? 'text-sm' : ''}">
							Privacy Protection
						</h4>
						<p
							class="text-gray-600 dark:text-gray-400 {preferences.enableCompact
								? 'text-xs'
								: 'text-sm'}"
						>
							Your browsing remains private. We don't store URLs or content, ensuring anonymity.
						</p>
					</div>
				</div>
			</div>
		</CardContent>
	</Card>
</div>
