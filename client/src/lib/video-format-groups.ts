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
// streams — on many sites those are everything above a low resolution and play
// silently. Users who want them (e.g. to download a high-res file and merge
// audio themselves) can flip the "Show video-only qualities" preference on.
// Also drops any format-group tab left with nothing to show once that filter
// applies.
export function visibleFormatGroups(
	video: GroupedVideo,
	preferences: Pick<Preferences, 'showVideoOnlyFormats'>
): FormatGroup[] {
	const groups = video.formatGroups
		.map((g) => ({
			type: g.type,
			qualities: preferences.showVideoOnlyFormats
				? g.qualities
				: g.qualities.filter((q) => !q.videoOnly)
		}))
		.filter((g) => g.qualities.length > 0)
		.sort((a, b) => groupRank(a.type) - groupRank(b.type));

	if (groups.length > 0) {
		return groups;
	}

	// Every format is video-only: the filter would leave an empty card (or drop
	// the video from the list entirely). Showing the silent streams — each
	// flagged "no sound" in the quality list — beats showing nothing.
	return video.formatGroups
		.filter((g) => g.qualities.length > 0)
		.map((g) => ({ type: g.type, qualities: g.qualities }))
		.sort((a, b) => groupRank(a.type) - groupRank(b.type));
}
