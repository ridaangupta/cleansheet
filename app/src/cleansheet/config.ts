import type { VideoSource } from '@AppServices/videoPlayer';
import type { Category } from '@Sidecar';

/**
 * Where streams, sidecars, textures and art come from: 'cloud' (CloudFront, cloud/template.yaml,
 * filled by cloud/publish_media.sh) or 'local' (cloud/mock_server.py on the dev Mac, for files not
 * published yet).
 */
export const MEDIA_SOURCE = 'cloud' as 'cloud' | 'local';
/** cloud/mock_server.py; 10.0.2.2 is the dev Mac as seen from the Vega Virtual Device. */
export const LOCAL_MEDIA_SERVER = 'http://10.0.2.2:8787';
export const CLOUD_MEDIA_SERVER = 'https://d3arzcz83y450c.cloudfront.net';
export const MEDIA_SERVER =
  MEDIA_SOURCE === 'cloud' ? CLOUD_MEDIA_SERVER : LOCAL_MEDIA_SERVER;

/**
 * Sponsor-inventory API (Lambda function URL, cloud/inventory/handler.py): viewer prefs per profile
 * and the replacement sponsor for each board slot. No sign-in: anyone with the URL can change prefs.
 */
export const INVENTORY_API =
  'https://w6ov4sbjyvia6nnypwlvos7rh40ogmaz.lambda-url.us-east-2.on.aws';
export const CLIP = 'tachira_02';

/**
 * Which sidecar track drives the overlay: 'ground_truth' (composite.py, exact, always confident) or
 * 'model' (pipeline/detect.py: the detector's tracked output, with real confidences, so 'auto'
 * blurs the unsure boards).
 */
export const SIDECAR_SOURCE = 'model' as 'ground_truth' | 'model';

const MODEL = SIDECAR_SOURCE === 'model';
export const SIDECAR_URL = `${MEDIA_SERVER}/media/${CLIP}/${MODEL ? 'sidecar.model.json' : 'sidecar.json'}`;
export const BRANDS_URL = `${MEDIA_SERVER}/assets/brands/brands.json`;
/** Per-board obscuring textures from pipeline/board_textures.py (index.json + blur/<id>.png). */
export const TEXTURES_URL = `${MEDIA_SERVER}/media/${CLIP}/${MODEL ? 'textures.model' : 'textures'}`;

/**
 * Hidden boards at or above this confidence get a replacement sponsor; below it, the board's
 * blurred texture (a replacement on a shaky detection would visibly swim).
 */
export const REPLACE_MIN_CONFIDENCE = 0.6;

/** Viewer defaults until the settings UI and prefs API exist: categories hidden at start. */
export const DEFAULT_HIDDEN: Category[] = ['gambling', 'alcohol'];

/**
 * Treatment per hidden category at start: 'auto' (replace when confident, else blur), 'replace' or
 * 'blur'. Ground-truth sidecars are always fully confident, so 'auto' only ever replaces; set a
 * category to 'blur' to show the blurred texture (e.g. a demo with gambling replaced, alcohol blurred).
 */
export const DEFAULT_TREATMENTS: Partial<
  Record<Category, 'auto' | 'replace' | 'blur'>
> = {};

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

/** Loop the clip instead of leaving the player when it ends (short demo clips, testing the panel). */
export const LOOP_CLIP = true;

/** Debug: outline every sidecar object's bbox in its category colour, treated or not. */
export const SHOW_BOXES = false;

export const SYNC_TEST_VIDEO = {
  title: 'Cleansheet sync test',
  type: 'hls',
  format: 'm3u8',
  // The burned-in test streams (make synctest) are only on the mock server.
  uri: `${LOCAL_MEDIA_SERVER}/media/${CLIP}/hls_tc/index.m3u8`,
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
