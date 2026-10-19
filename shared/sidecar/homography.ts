import type { BBox, Point, Quad } from './types';

/** Row-major 3x3 projective matrix acting on column vectors [x, y, 1]. */
export type Mat3 = [number, number, number, number, number, number, number, number, number];

/**
 * Homography mapping the unit square (0,0) (1,0) (1,1) (0,1) onto `quad`
 * (top-left, top-right, bottom-right, bottom-left). Heckbert's closed form.
 */
export function squareToQuad(quad: Quad): Mat3 {
  const [[x0, y0], [x1, y1], [x2, y2], [x3, y3]] = quad;
  const sx = x0 - x1 + x2 - x3;
  const sy = y0 - y1 + y2 - y3;
  if (Math.abs(sx) < 1e-12 && Math.abs(sy) < 1e-12) {
    return [x1 - x0, x3 - x0, x0, y1 - y0, y3 - y0, y0, 0, 0, 1];
  }
  const dx1 = x1 - x2;
  const dx2 = x3 - x2;
  const dy1 = y1 - y2;
  const dy2 = y3 - y2;
  const den = dx1 * dy2 - dx2 * dy1;
  const g = (sx * dy2 - dx2 * sy) / den;
  const h = (dx1 * sy - sx * dy1) / den;
  return [x1 - x0 + g * x1, x3 - x0 + h * x3, x0, y1 - y0 + g * y1, y3 - y0 + h * y3, y0, g, h, 1];
}

/** Homography mapping the rectangle (0,0)-(w,h) onto `quad`. */
export function rectToQuad(w: number, h: number, quad: Quad): Mat3 {
  const m = squareToQuad(quad);
  return [m[0] / w, m[1] / h, m[2], m[3] / w, m[4] / h, m[5], m[6] / w, m[7] / h, m[8]];
}

export function applyHomography(m: Mat3, [x, y]: Point): Point {
  const w = m[6] * x + m[7] * y + m[8];
  return [(m[0] * x + m[1] * y + m[2]) / w, (m[3] * x + m[4] * y + m[5]) / w];
}

/**
 * CSS `matrix3d(...)` that warps an element of size w x h onto `quad`
 * (pixel coordinates in the element's containing block). The element needs
 * `transform-origin: 0 0`.
 */
export function cssMatrix3d(w: number, h: number, quad: Quad): string {
  // Significant digits, not fixed decimals: the projective terms are tiny.
  return `matrix3d(${matrix4(w, h, quad).map((v) => +v.toPrecision(12)).join(',')})`;
}

/**
 * The same warp as `cssMatrix3d`, as the 16-number column-major array React Native's
 * `transform: [{matrix}]` takes. Needs `transformOrigin: 'left top'` on the element.
 */
export function matrix4(w: number, h: number, quad: Quad): number[] {
  const m = rectToQuad(w, h, quad);
  // 4x4 column-major, with the projective row mapped to the w component.
  return [m[0], m[3], 0, m[6], m[1], m[4], 0, m[7], 0, 0, 1, 0, m[2], m[5], 0, m[8]];
}

/**
 * `quad` grown outward by about `px` on every side, measured in the quad's own pixel units
 * (pass a pixel quad). Done in the board's plane (through its homography), so a thin, tilted
 * board grows evenly on all four sides and the overlay hides the real board's edges.
 */
export function growQuad(quad: Quad, px: number): Quad {
  const [tl, tr, br, bl] = quad;
  const len = (a: Point, b: Point) => Math.hypot(b[0] - a[0], b[1] - a[1]);
  const du = px / Math.max((len(tl, tr) + len(bl, br)) / 2, 1e-6);
  const dv = px / Math.max((len(tl, bl) + len(tr, br)) / 2, 1e-6);
  const m = squareToQuad(quad);
  return [
    applyHomography(m, [-du, -dv]),
    applyHomography(m, [1 + du, -dv]),
    applyHomography(m, [1 + du, 1 + dv]),
    applyHomography(m, [-du, 1 + dv]),
  ];
}

/**
 * True if `quad` is strictly convex. A warp onto a non-convex or collapsed quad (e.g. corners a
 * model couldn't place) sends the image across the screen, so renderers should skip it.
 */
export function isConvexQuad(quad: Quad): boolean {
  let sign = 0;
  for (let i = 0; i < 4; i++) {
    const [a, b, c] = [quad[i]!, quad[(i + 1) % 4]!, quad[(i + 2) % 4]!];
    const cross = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]);
    if (Math.abs(cross) < 1e-9) return false;
    if (sign === 0) sign = Math.sign(cross);
    else if (Math.sign(cross) !== sign) return false;
  }
  return true;
}

/**
 * How much farther away the board's far end is than its near end: the ratio of the largest to the
 * smallest projective weight over its corners (1 = no perspective). Infinity if the quad's plane
 * folds through the horizon. Unaffected by scaling, so normalized and pixel quads agree.
 */
export function foreshortening(quad: Quad): number {
  const m = squareToQuad(quad);
  const ws = [m[8], m[6] + m[8], m[6] + m[7] + m[8], m[7] + m[8]];
  const lo = Math.min(...ws);
  const hi = Math.max(...ws);
  return lo > 0 ? hi / lo : Infinity; // the top-left weight is always 1
}

/** Real boards stay under ~1.2; past this the quad is a detector error (a corner nearly on another). */
export const MAX_FORESHORTENING = 2;

/**
 * True if a warp onto `quad` draws something board-shaped: convex, and not so foreshortened that
 * the warp's far corner runs off toward infinity. Vega draws such a warp as a triangle across the
 * screen, so renderers should skip the quad.
 */
export function isRenderableQuad(quad: Quad): boolean {
  return isConvexQuad(quad) && foreshortening(quad) <= MAX_FORESHORTENING;
}

/** [x, y, w, h] of the part of a normalized `quad` inside the frame (0..1); zero-size if none is. */
export function visibleBBox(quad: Quad): BBox {
  const xs = quad.map((p) => Math.min(Math.max(p[0], 0), 1));
  const ys = quad.map((p) => Math.min(Math.max(p[1], 0), 1));
  const x = Math.min(...xs);
  const y = Math.min(...ys);
  return [x, y, Math.max(...xs) - x, Math.max(...ys) - y];
}
