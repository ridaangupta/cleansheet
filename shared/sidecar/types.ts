// Mirrors shared/sidecar/schema.json. Keep the two in sync.

export type Category = 'gambling' | 'alcohol' | 'neutral';
export type Kind = 'board' | 'jersey';

export type Point = [number, number];
/** Corners in order top-left, top-right, bottom-right, bottom-left. */
export type Quad = [Point, Point, Point, Point];
/** [x, y, w, h] */
export type BBox = [number, number, number, number];

export interface SidecarObject {
  /** Track id, stable across frames for the same physical sponsor. */
  id: string;
  kind: Kind;
  category: Category;
  brand?: string;
  /** Normalized to the video frame (0..1); may extend past the edges. */
  quad: Quad;
  /** Visible region, normalized and clipped to the frame. */
  bbox?: BBox;
  confidence: number;
}

export interface SidecarFrame {
  /** Media time in seconds. */
  t: number;
  objects: SidecarObject[];
}

export interface SidecarTrack {
  version: 1;
  video_id: string;
  source?: 'ground_truth' | 'model';
  fps: number;
  width: number;
  height: number;
  /** Sorted by ascending t. */
  frames: SidecarFrame[];
}
