import { describe, expect, it } from 'vitest';
import { applyHomography, cssMatrix3d, growQuad, isConvexQuad, rectToQuad, squareToQuad, visibleBBox } from './homography';
import type { Point, Quad } from './types';

const perspective: Quad = [
  [100, 50],
  [420, 80],
  [400, 160],
  [90, 140],
];

function expectPoint(actual: Point, expected: Point) {
  expect(actual[0]).toBeCloseTo(expected[0], 6);
  expect(actual[1]).toBeCloseTo(expected[1], 6);
}

describe('squareToQuad', () => {
  it('maps unit square corners onto a perspective quad', () => {
    const m = squareToQuad(perspective);
    const square: Point[] = [
      [0, 0],
      [1, 0],
      [1, 1],
      [0, 1],
    ];
    square.forEach((p, i) => expectPoint(applyHomography(m, p), perspective[i]));
  });

  it('handles parallelograms (affine case)', () => {
    const para: Quad = [
      [10, 10],
      [110, 20],
      [120, 70],
      [20, 60],
    ];
    const m = squareToQuad(para);
    expect(m[6]).toBe(0);
    expect(m[7]).toBe(0);
    expectPoint(applyHomography(m, [1, 1]), [120, 70]);
  });
});

describe('rectToQuad', () => {
  it('maps rectangle corners onto the quad', () => {
    const m = rectToQuad(800, 200, perspective);
    expectPoint(applyHomography(m, [0, 0]), perspective[0]);
    expectPoint(applyHomography(m, [800, 0]), perspective[1]);
    expectPoint(applyHomography(m, [800, 200]), perspective[2]);
    expectPoint(applyHomography(m, [0, 200]), perspective[3]);
  });
});

describe('cssMatrix3d', () => {
  it('lays out the homography column-major', () => {
    const m = rectToQuad(800, 200, perspective);
    const values = cssMatrix3d(800, 200, perspective)
      .slice('matrix3d('.length, -1)
      .split(',')
      .map(Number);
    expect(values).toHaveLength(16);
    // Apply as CSS would: [x', y', z', w'] = M * [x, y, 0, 1].
    const [x, y] = [800, 200];
    const xp = values[0] * x + values[4] * y + values[12];
    const yp = values[1] * x + values[5] * y + values[13];
    const wp = values[3] * x + values[7] * y + values[15];
    expectPoint([xp / wp, yp / wp], applyHomography(m, [x, y]));
  });
});

describe('growQuad', () => {
  it('grows an axis-aligned rectangle by px on every side', () => {
    const rect: Quad = [
      [10, 20],
      [110, 20],
      [110, 45],
      [10, 45],
    ];
    const g = growQuad(rect, 2);
    expectPoint(g[0], [8, 18]);
    expectPoint(g[2], [112, 47]);
  });

  it('keeps a perspective quad in its plane and contains the original', () => {
    const g = growQuad(perspective, 1.5);
    // Each grown corner moved outward, by a few px, not more.
    perspective.forEach((p, i) => {
      const d = Math.hypot(g[i][0] - p[0], g[i][1] - p[1]);
      expect(d).toBeGreaterThan(1);
      expect(d).toBeLessThan(6);
    });
    // Every original corner lies inside the grown quad (same side of all four edges).
    const cross = (a: Point, b: Point, p: Point) => (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]);
    perspective.forEach((p) => {
      const sides = g.map((a, i) => Math.sign(cross(a, g[(i + 1) % 4], p)));
      expect(new Set(sides).size).toBe(1);
    });
  });
});

describe('isConvexQuad', () => {
  it('accepts a perspective board', () => {
    expect(isConvexQuad(perspective)).toBe(true);
  });

  it('rejects a bow-tie and a collapsed edge', () => {
    // Off-screen corners a model couldn't place (metro_ucv_01, left edge).
    expect(isConvexQuad([[1, 134], [2, 138], [11, 160], [0, 146]])).toBe(false);
    expect(isConvexQuad([[0, 0], [10, 0], [10, 0], [0, 10]])).toBe(false);
  });
});

describe('visibleBBox', () => {
  it('clips a quad that runs off the frame', () => {
    const [x, y, w, h] = visibleBBox([[-0.1, 0.2], [0.3, 0.2], [0.3, 0.3], [-0.1, 0.3]]);
    expect([x, y]).toEqual([0, 0.2]);
    expect(w).toBeCloseTo(0.3);
    expect(h).toBeCloseTo(0.1);
  });
});
