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
}

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
  const time = t + (options.offset ?? 0);

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
