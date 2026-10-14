import { describe, expect, it } from 'vitest';
import { filterObjects, frameIndexAt, objectsAt, parseSidecar, samplesVideoFrames } from './sync';
import type { Quad, SidecarFile, SidecarObject, SidecarTrack } from './types';

function quadAt(x: number): Quad {
  return [
    [x, 0.1],
    [x + 0.2, 0.1],
    [x + 0.2, 0.2],
    [x, 0.2],
  ];
}

function obj(id: string, x: number, extra: Partial<SidecarObject> = {}): SidecarObject {
  return { id, kind: 'board', category: 'gambling', quad: quadAt(x), confidence: 1, ...extra };
}

function track(frames: SidecarTrack['frames']): SidecarTrack {
  return { video_id: 'test', fps: 30, width: 1280, height: 720, frames };
}

describe('parseSidecar', () => {
  const file: SidecarFile = {
    version: 2,
    video_id: 'test',
    source: 'model',
    fps: 30,
    width: 1280,
    height: 720,
    tracks: { a: { kind: 'board', category: 'gambling', brand: 'BetNova', confidence: 0.9 } },
    frames: [
      { t: 0, objects: [{ id: 'a', quad: quadAt(0) }] },
      { t: 1 / 30, objects: [] },
    ],
  };

  it('joins each object with its track', () => {
    const tr = parseSidecar(file);
    expect(tr.frames[0]!.objects[0]).toEqual({ ...file.tracks.a, id: 'a', quad: quadAt(0) });
    expect(tr.frames[1]!.objects).toEqual([]);
    expect(tr.source).toBe('model');
  });

  it('rejects unknown ids and versions', () => {
    const orphan = { ...file, frames: [{ t: 0, objects: [{ id: 'b', quad: quadAt(0) }] }] };
    expect(() => parseSidecar(orphan)).toThrow(/b has no entry/);
    expect(() => parseSidecar({ ...file, version: 1 } as unknown as SidecarFile)).toThrow(/version 1/);
  });
});

describe('frameIndexAt', () => {
  const frames = Array.from({ length: 101 }, (_, i) => ({ t: i * 0.1, objects: [] }));
  it('finds the frame at or before t', () => {
    expect(frameIndexAt(frames, -1)).toBe(-1);
    expect(frameIndexAt(frames, 0)).toBe(0);
    expect(frameIndexAt(frames, 0.55)).toBe(5);
    expect(frameIndexAt(frames, 3.0)).toBe(30);
    expect(frameIndexAt(frames, 99)).toBe(100);
  });
});

describe('objectsAt', () => {
  const tr = track([
    { t: 1.0, objects: [obj('a', 0.0), obj('gone', 0.5)] },
    { t: 1.1, objects: [obj('a', 0.1), obj('new', 0.7)] },
  ]);

  it('interpolates objects present in both frames', () => {
    const [a] = objectsAt(tr, 1.05).filter((o) => o.id === 'a');
    expect(a.quad[0][0]).toBeCloseTo(0.05);
    expect(a.quad[2][0]).toBeCloseTo(0.25);
  });

  it('returns exact frames at their timestamps', () => {
    expect(objectsAt(tr, 1.0).map((o) => o.id).sort()).toEqual(['a', 'gone']);
    expect(objectsAt(tr, 1.1).map((o) => o.id).sort()).toEqual(['a', 'new']);
  });

  it('swaps one-sided objects at the midpoint', () => {
    expect(objectsAt(tr, 1.04).map((o) => o.id).sort()).toEqual(['a', 'gone']);
    expect(objectsAt(tr, 1.06).map((o) => o.id).sort()).toEqual(['a', 'new']);
  });

  it('holds the ends of the track briefly, then clears', () => {
    expect(objectsAt(tr, 0.8)).toHaveLength(2);
    expect(objectsAt(tr, 0.7)).toHaveLength(0);
    expect(objectsAt(tr, 1.3)).toHaveLength(2);
    expect(objectsAt(tr, 1.4)).toHaveLength(0);
  });

  it('applies the offset before lookup', () => {
    const [a] = objectsAt(tr, 1.0, { offset: 0.05 }).filter((o) => o.id === 'a');
    expect(a.quad[0][0]).toBeCloseTo(0.05);
  });

  it('does not interpolate across gaps larger than maxGap', () => {
    const gappy = track([
      { t: 0, objects: [obj('a', 0)] },
      { t: 2, objects: [obj('a', 1)] },
    ]);
    expect(objectsAt(gappy, 0.2)[0].quad[0][0]).toBe(0);
    expect(objectsAt(gappy, 1.0)).toHaveLength(0);
    expect(objectsAt(gappy, 1.9)[0].quad[0][0]).toBe(1);
    // With a larger maxGap the same track interpolates.
    expect(objectsAt(gappy, 1.0, { maxGap: 3 })[0].quad[0][0]).toBeCloseTo(0.5);
  });

  it('interpolates confidence', () => {
    const t2 = track([
      { t: 0, objects: [obj('a', 0, { confidence: 0.6 })] },
      { t: 0.1, objects: [obj('a', 0.1, { confidence: 0.8 })] },
    ]);
    const [a] = objectsAt(t2, 0.05);
    expect(a.confidence).toBeCloseTo(0.7);
  });

  it('snaps to the frame on screen when interpolate is false', () => {
    const [a] = objectsAt(tr, 1.09, { interpolate: false }).filter((o) => o.id === 'a');
    expect(a.quad[0][0]).toBe(0);
    expect(objectsAt(tr, 1.09, { interpolate: false }).map((o) => o.id).sort()).toEqual(['a', 'gone']);
  });

  it('snaps to a frame whose stored t was rounded up', () => {
    // 2/30 = 0.0666..., stored rounded as 0.066667: at exactly 2/30 the video shows frame 2.
    const rounded = track([
      { t: 0, objects: [obj('a', 0)] },
      { t: 0.033333, objects: [obj('a', 0.1)] },
      { t: 0.066667, objects: [obj('a', 0.2)] },
    ]);
    expect(objectsAt(rounded, 2 / 30, { interpolate: false })[0].quad[0][0]).toBe(0.2);
    expect(objectsAt(rounded, 0.05, { interpolate: false })[0].quad[0][0]).toBe(0.1);
  });

  it('still holds track ends and gaps when snapping', () => {
    expect(objectsAt(tr, 1.3, { interpolate: false })).toHaveLength(2);
    expect(objectsAt(tr, 1.4, { interpolate: false })).toHaveLength(0);
  });

  it('handles an empty track', () => {
    expect(objectsAt(track([]), 1)).toEqual([]);
  });
});

describe('samplesVideoFrames', () => {
  it('is true for a per-frame track and false for a 5 Hz one', () => {
    const perFrame = track(Array.from({ length: 31 }, (_, i) => ({ t: i / 30, objects: [] })));
    const sparse = track(Array.from({ length: 6 }, (_, i) => ({ t: i / 5, objects: [] })));
    expect(samplesVideoFrames(perFrame)).toBe(true);
    expect(samplesVideoFrames(sparse)).toBe(false);
  });
});

describe('filterObjects', () => {
  const objects = [
    obj('g', 0, { category: 'gambling', brand: 'BetNova' }),
    obj('al', 0, { category: 'alcohol', brand: 'Hopfield Lager' }),
    obj('n', 0, { category: 'neutral', brand: 'Northpeak Mobile' }),
    obj('low', 0, { category: 'gambling', confidence: 0.2 }),
  ];

  it('keeps hidden categories and blocked brands', () => {
    const out = filterObjects(objects, {
      categories: new Set(['gambling']),
      blockedBrands: new Set(['Northpeak Mobile']),
      minConfidence: 0.5,
    });
    expect(out.map((o) => o.id)).toEqual(['g', 'n']);
  });
});
