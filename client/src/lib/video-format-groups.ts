/** Shared by VideoExtractList (deciding which cards to group/show) and
 *  VideoCard (deciding which tabs/qualities to render) -- kept in one place
 *  so the two can't drift on what "visible" means for a card. */

import { isAudioType } from '$lib/format';
import type { FormatGroup, GroupedVideo, Preferences } from '$lib/types';

// Tab/list order: easiest-to-play first (progressive MP4 -- universal
// browser support, no special handling), then everything else that still
// needs some extra work to play (WebM/MKV/HLS/...), audio-only last.
export function groupRank(type: string): number {
	if (isAudioType(type)) {
		return 2;
	}

	return type === 'video/mp4' ? 0 : 1;
}

// Qualities to actually show. By default we hide adaptive video-only (no-audio)
// streams — on YouTube those are everything above 360p and play silently. Users
// who want them (e.g. to download a high-res file and merge audio themselves)
// can flip the "Show video-only qualities" preference on. Also drops any
// format-group tab left with nothing to show once that filter applies.
export function visibleFormatGroups(
	video: GroupedVideo,
	preferences: Pick<Preferences, 'showVideoOnlyFormats'>
): FormatGroup[] {
	return video.formatGroups
		.map((g) => ({
			type: g.type,
			qualities: preferences.showVideoOnlyFormats
				? g.qualities
				: g.qualities.filter((q) => !q.videoOnly)
		}))
		.filter((g) => g.qualities.length > 0)
		.sort((a, b) => groupRank(a.type) - groupRank(b.type));
}
