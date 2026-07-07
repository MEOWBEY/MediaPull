/** Reactive `matchMedia` flag, shared by anything that needs to switch layout
 *  at a breakpoint (e.g. side-sheet on desktop vs bottom-sheet on mobile).
 *  Defaults to `true` so SSR/first paint prefers the desktop layout, matching
 *  how the rest of the app treats `sm:` as the baseline breakpoint. */

import { browser } from '$app/environment';

export class MediaQuery {
	matches = $state(true);

	constructor(query: string) {
		if (!browser) {return;}

		const mql = window.matchMedia(query);

		this.matches = mql.matches;
		mql.addEventListener('change', (e) => (this.matches = e.matches));
	}
}
