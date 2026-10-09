import type { BBox, Category, Quad, SidecarFrame, SidecarObject, SidecarTrack } from './types';

export interface SyncOptions {
  /**
   * Seconds added to the player clock before lookup. Use it to calibrate a
   * constant skew between the player's currentTime and the sidecar timeline.
   */
  offset?: number;
  /**
   * Largest gap (seconds) between sidecar frames that is still interpolated.
   * Past the ends of the track, or across a larger gap, objects are held for
   * at most half of this before disappearing.
   */
  maxGap?: number;
  /**
   * Interpolate between neighbouring sidecar frames (default true). Turn it off for a track
   * sampled at the video frame rate (see `samplesVideoFrames`): the video shows whole frames,
   * so interpolating makes the overlay slide while the picture holds still. Keep it on for
   * sparse tracks (a 5-10 Hz model sidecar).
   */
  interpolate?: boolean;
}

/**
 * Snapped lookups add this before searching, so a time exactly on a frame boundary finds that
 * frame even when its `t` was rounded up (e.g. 2/30 stored as 0.066667).
 */
const SNAP_EPSILON = 1e-3;

const DEFAULT_MAX_GAP = 0.5;

/** Index of the last frame with frame.t <= t, or -1 if t is before the first frame. */
export function frameIndexAt(frames: readonly SidecarFrame[], t: number): number {
  let lo = 0;
  let hi = frames.length - 1;
  let found = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (frames[mid]!.t <= t) {
      found = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return found;
}

/**
 * Objects to draw at player time `t`. Objects present in both neighbouring
 * frames are linearly interpolated; objects present in only one are shown
 * for the half of the interval closest to that frame.
 */
export function objectsAt(track: SidecarTrack, t: number, options: SyncOptions = {}): SidecarObject[] {
  const frames = track.frames;
  if (frames.length === 0) return [];
  const maxGap = options.maxGap ?? DEFAULT_MAX_GAP;
  const hold = maxGap / 2;
  const interpolate = options.interpolate ?? true;
  const time = t + (options.offset ?? 0) + (interpolate ? 0 : SNAP_EPSILON);

  const i = frameIndexAt(frames, time);
  if (i === -1) {
    return frames[0]!.t - time <= hold ? frames[0]!.objects : [];
  }
  const a = frames[i]!;
  if (i === frames.length - 1) {
    return time - a.t <= hold ? a.objects : [];
  }
  const b = frames[i + 1]!;
  const dt = b.t - a.t;

  if (dt > maxGap) {
    if (time - a.t <= hold) return a.objects;
    if (b.t - time <= hold) return b.objects;
    return [];
  }

  if (!interpolate) return a.objects;

  const alpha = dt > 0 ? (time - a.t) / dt : 0;
  const next = new Map(b.objects.map((o) => [o.id, o]));
  const out: SidecarObject[] = [];
  for (const oa of a.objects) {
    const ob = next.get(oa.id);
    if (ob) {
      out.push(lerpObject(oa, ob, alpha));
      next.delete(oa.id);
    } else if (alpha < 0.5) {
      out.push(oa);
    }
  }
  if (alpha >= 0.5) out.push(...next.values());
  return out;
}

/** True when the track has a sample for (nearly) every video frame, so lookups should snap. */
export function samplesVideoFrames(track: SidecarTrack): boolean {
  const f = track.frames;
  if (f.length < 2) return false;
  const hz = (f.length - 1) / (f[f.length - 1]!.t - f[0]!.t);
  return hz >= 0.9 * track.fps;
}

export interface FilterPrefs {
  /** Categories the viewer wants hidden. */
  categories: ReadonlySet<Category>;
  /** Extra brand names the viewer wants hidden regardless of category. */
  blockedBrands?: ReadonlySet<string>;
  minConfidence?: number;
}

export function filterObjects(objects: readonly SidecarObject[], prefs: FilterPrefs): SidecarObject[] {
  const minConfidence = prefs.minConfidence ?? 0;
  return objects.filter(
    (o) =>
      o.confidence >= minConfidence &&
      (prefs.categories.has(o.category) || (o.brand !== undefined && (prefs.blockedBrands?.has(o.brand) ?? false))),
  );
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

function lerpObject(a: SidecarObject, b: SidecarObject, t: number): SidecarObject {
  const quad = a.quad.map((p, k) => [lerp(p[0], b.quad[k]![0], t), lerp(p[1], b.quad[k]![1], t)]) as Quad;
  const out: SidecarObject = { ...(t < 0.5 ? a : b), quad, confidence: lerp(a.confidence, b.confidence, t) };
  if (a.bbox && b.bbox) {
    out.bbox = a.bbox.map((v, k) => lerp(v, b.bbox![k]!, t)) as BBox;
  }
  return out;
}
