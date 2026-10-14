// Mirrors shared/sidecar/schema.json. Keep the two in sync.

export type Category = 'gambling' | 'alcohol' | 'neutral';
export type Kind = 'board' | 'jersey';
export type Source = 'ground_truth' | 'model';

export type Point = [number, number];
/** Corners in order top-left, top-right, bottom-right, bottom-left. */
export type Quad = [Point, Point, Point, Point];
/** [x, y, w, h] */
export type BBox = [number, number, number, number];

/** Per-sponsor attributes, stored once per track id. */
export interface TrackInfo {
  kind: Kind;
  category: Category;
  brand?: string;
  /** One value for the whole track, so a sponsor doesn't flicker between treatments. */
  confidence: number;
}

/** The sidecar file as served (schema.json, version 2). Parse it with `parseSidecar`. */
export interface SidecarFile {
  version: 2;
  video_id: string;
  source?: Source;
  fps: number;
  width: number;
  height: number;
  tracks: Record<string, TrackInfo>;
  /** Sorted by ascending t. */
  frames: { t: number; objects: { id: string; quad: Quad }[] }[];
}

/** One sponsor on one frame, with its track's attributes joined in. */
export interface SidecarObject extends TrackInfo {
  /** Track id, stable across frames for the same physical sponsor. */
  id: string;
  /** Normalized to the video frame (0..1); may extend past the edges. */
  quad: Quad;
}

export interface SidecarFrame {
  /** Media time in seconds. */
  t: number;
  objects: SidecarObject[];
}

/** A parsed sidecar: every frame's objects carry their track's attributes. */
export interface SidecarTrack {
  video_id: string;
  source?: Source;
  fps: number;
  width: number;
  height: number;
  /** Sorted by ascending t. */
  frames: SidecarFrame[];
}
