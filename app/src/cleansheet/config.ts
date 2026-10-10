import type { VideoSource } from '@AppServices/videoPlayer';

/** cloud/mock_server.py on the dev Mac; 10.0.2.2 is the host as seen from the Vega Virtual Device. */
export const MEDIA_SERVER = 'http://10.0.2.2:8787';
export const CLIP = 'tachira_02';

export const SIDECAR_URL = `${MEDIA_SERVER}/media/${CLIP}/sidecar.json`;
export const BRANDS_URL = `${MEDIA_SERVER}/assets/brands/brands.json`;
/** Per-board obscuring textures from pipeline/board_textures.py (index.json + blur/<id>.png). */
export const TEXTURES_URL = `${MEDIA_SERVER}/media/${CLIP}/textures`;

/**
 * Hidden boards at or above this confidence get a replacement sponsor; below it, the board's
 * blurred texture (a replacement on a shaky detection would visibly swim).
 */
export const REPLACE_MIN_CONFIDENCE = 0.6;

/** Dev/demo override of the treatment choice: 'auto' follows confidence. */
export const FORCE_TREATMENT: 'auto' | 'replace' | 'blur' = 'auto';

/**
 * Seconds added to the player's currentTime before looking up the sidecar track.
 * Measured on the Vega Virtual Device (SDK 0.24) with burned-in frame numbers: currentTime trails
 * the displayed frame by 3-4 frames at 30 fps. 0.1 s left the overlay one frame behind in 4 of 8
 * samples; 0.117 s (3.5 frames) put it on the displayed frame in 8 of 12, one off either side in
 * the rest (2026-10-09, tachira_02, snapped lookups). Re-measure on hardware.
 */
export const SYNC_OFFSET_S = 0.117;

/**
 * Sync test mode: every stream plays the clip with burned-in frame numbers
 * (pipeline/burn_frames.py -> media/<clip>/hls_tc) and the overlay draws a HUD
 * with the frame it is rendering, so a screenshot shows the sync error in frames.
 */
export const SYNC_TEST = false;


/**
 * Log the player time of every overlay render (`[cleansheet-sync] <t>`) to the device log, for
 * measuring where in the video frame renders land (read with `loggingctl log -v <package>`).
 */
export const SYNC_LOG = false;

/** Draw the HUD (frame, loop and update rates) outside the sync test too. */
export const SHOW_STATS = false;

/** Debug: outline every sidecar object's bbox in its category colour, treated or not. */
export const SHOW_BOXES = false;

export const SYNC_TEST_VIDEO = {
  title: 'Cleansheet sync test',
  type: 'hls',
  format: 'm3u8',
  uri: `${MEDIA_SERVER}/media/${CLIP}/hls_tc/index.m3u8`,
  autoplay: true,
} as const satisfies VideoSource;

/** The clip every stream plays while Cleansheet is in development. */
export const CLIP_VIDEO = {
  title: `Cleansheet ${CLIP}`,
  type: 'hls',
  format: 'm3u8',
  uri: `${MEDIA_SERVER}/media/${CLIP}/hls/index.m3u8`,
  autoplay: true,
} as const satisfies VideoSource;
