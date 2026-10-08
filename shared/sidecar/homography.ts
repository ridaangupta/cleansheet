import type { Point, Quad } from './types';

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
  const m = rectToQuad(w, h, quad);
  // 4x4 column-major, with the projective row mapped to the w component.
  const cols = [m[0], m[3], 0, m[6], m[1], m[4], 0, m[7], 0, 0, 1, 0, m[2], m[5], 0, m[8]];
  // Significant digits, not fixed decimals: the projective terms are tiny.
  return `matrix3d(${cols.map((v) => +v.toPrecision(12)).join(',')})`;
}
