/**
 * Per-key "is this group currently refreshing" tracker -- shared by
 * VideoExtractList and GalleryExtractList, which both re-pull a stale
 * source group and only clear the busy flag once the task settles.
 */

import { SvelteMap } from 'svelte/reactivity';

export class GroupRefreshTracker<K> {
	private readonly refreshing = new SvelteMap<K, boolean>();

	isRefreshing(key: K): boolean {
		return this.refreshing.get(key) ?? false;
	}

	/** Runs `task` for `key`, no-op if a refresh for that key is already in
	 *  flight. Always clears the busy flag, even if `task` throws. */
	async run(key: K, task: () => Promise<void>): Promise<void> {
		if (this.isRefreshing(key)) {
			return;
		}

		this.refreshing.set(key, true);

		try {
			await task();
		} finally {
			this.refreshing.set(key, false);
		}
	}
}
