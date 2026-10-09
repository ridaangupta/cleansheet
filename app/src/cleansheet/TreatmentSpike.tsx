// Step 3 spike: what can the Vega renderer do for the replace/blur treatments?
//  1. Live warp: a replacement sponsor warped onto every sidecar board with transform: [{matrix}]
//     (projective), red dots at the true quad corners. Image corners on the dots = warp works.
//  2. Test card: a fixed, strongly keystoned target with corner dots, so a renderer that drops
//     the perspective terms shows up even when live boards are nearly rectangular.
//  3. Blur: the same image with and without blurRadius.
// Screenshot with scripts/vvd_screenshot.sh and compare.

import React, { memo, useEffect, useMemo, useState } from 'react';
import { Image, StyleSheet, Text, View } from 'react-native';

import { growQuad, matrix4, type Quad, type SidecarObject } from '@Sidecar';

import { CLIP, MEDIA_SERVER, SPIKE_MODE } from './config';

type Brand = { name: string; category: string; file: string };

type Props = { objects: SidecarObject[]; width: number; height: number };

// Corner dots on the live boards (~4 views per board) for checking alignment; off for perf runs.
const SHOW_DOTS = false;

const TEST_QUAD: Quad = [
  [60, 40],
  [380, 90],
  [370, 200],
  [70, 230],
];

function hashIndex(id: string, n: number): number {
  let h = 2166136261;
  for (let i = 0; i < id.length; i++) h = Math.imul(h ^ id.charCodeAt(i), 16777619);
  return Math.abs(h) % n;
}

const Dot = ({ x, y }: { x: number; y: number }) => (
  <View style={[styles.dot, { left: x - 4, top: y - 4 }]} />
);

type WarpedProps = {
  uri: string;
  size: [number, number];
  /** Corners, normalized (sidecar quads) or in px with scale 1. */
  quad: Quad;
  scaleX: number;
  scaleY: number;
  /** Grow the warped image this many screen px past the quad on every side (hides real board edges). */
  grow?: number;
};

// Memoized: with a snapped sidecar the quad array is the same object until its frame changes, so a
// board re-renders and recomputes its matrix once per sidecar frame, not on every parent render.
const Warped = memo(({ uri, size, quad, scaleX, scaleY, grow = 0 }: WarpedProps) => {
  const matrix = useMemo(() => {
    const px = quad.map(([x, y]) => [x * scaleX, y * scaleY]) as Quad;
    return matrix4(size[0], size[1], grow ? growQuad(px, grow) : px);
  }, [size, quad, scaleX, scaleY, grow]);
  return (
    <Image
      source={{ uri }}
      style={[styles.warped, { width: size[0], height: size[1], transform: [{ matrix }] }]}
    />
  );
});

export const TreatmentSpike = ({ objects, width, height }: Props) => {
  const [brands, setBrands] = useState<{ size: [number, number]; replacements: Brand[] } | null>(null);
  // Board id -> texture size, built once so Warped's memo sees the same tuple every render.
  const [textures, setTextures] = useState<Record<string, [number, number]> | null>(null);

  useEffect(() => {
    fetch(`${MEDIA_SERVER}/assets/brands/brands.json`)
      .then((r) => r.json() as Promise<{ size: [number, number]; brands: Brand[] }>)
      .then((d) => setBrands({ size: d.size, replacements: d.brands.filter((b) => b.category === 'replacement') }))
      .catch(() => undefined);
    if (SPIKE_MODE !== 'replace') {
      fetch(`${MEDIA_SERVER}/media/${CLIP}/textures/index.json`)
        .then((r) => r.json() as Promise<Record<string, { w: number; h: number }>>)
        .then((idx) => setTextures(Object.fromEntries(Object.entries(idx).map(([id, t]) => [id, [t.w, t.h]]))))
        .catch(() => undefined);
    }
  }, []);

  if (SPIKE_MODE !== 'replace') {
    // Obscuring mock-up: each board's own cloud-made texture, warped onto its quad grown by 1.5 px.
    if (!textures) return null;
    return (
      <>
        {objects.map((o) => {
          const t = textures[o.id];
          if (!t) return null;
          return (
            <Warped
              key={o.id}
              uri={`${MEDIA_SERVER}/media/${CLIP}/textures/${SPIKE_MODE}/${o.id}.png`}
              size={t}
              quad={o.quad}
              scaleX={width}
              scaleY={height}
              grow={1.5}
            />
          );
        })}
      </>
    );
  }

  if (!brands) return null;
  const uriFor = (b: Brand) => `${MEDIA_SERVER}/assets/brands/${b.file}`;

  return (
    <>
      {/* 1. live warp onto sidecar boards */}
      {objects.map((o) => {
        const b = brands.replacements[hashIndex(o.id, brands.replacements.length)]!;
        return <Warped key={o.id} uri={uriFor(b)} size={brands.size} quad={o.quad} scaleX={width} scaleY={height} />;
      })}
      {SHOW_DOTS &&
        objects.map((o) => o.quad.map(([x, y], k) => <Dot key={`${o.id}-${k}`} x={x * width} y={y * height} />))}

      {/* 2. fixed keystone test card */}
      <View style={[styles.card, { left: width - 460, top: height - 300 }]}>
        <Warped uri={uriFor(brands.replacements[0]!)} size={brands.size} quad={TEST_QUAD} scaleX={1} scaleY={1} />
        {TEST_QUAD.map(([x, y], k) => (
          <Dot key={k} x={x} y={y} />
        ))}
        <Text style={styles.label}>matrix warp: image corners should sit on the red dots</Text>
      </View>

      {/* 3. blurRadius */}
      <View style={[styles.blurRow, { top: height - 170 }]}>
        <View>
          <Image source={{ uri: uriFor(brands.replacements[1]!) }} style={styles.blurImg} />
          <Text style={styles.label}>blurRadius 0</Text>
        </View>
        <View>
          <Image source={{ uri: uriFor(brands.replacements[1]!) }} style={styles.blurImg} blurRadius={8} />
          <Text style={styles.label}>blurRadius 8</Text>
        </View>
      </View>
    </>
  );
};

const styles = StyleSheet.create({
  warped: {
    position: 'absolute',
    left: 0,
    top: 0,
    transformOrigin: 'left top',
  },
  dot: {
    position: 'absolute',
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: '#ff0000',
  },
  card: {
    position: 'absolute',
    width: 440,
    height: 280,
    backgroundColor: 'rgba(0,0,0,0.6)',
  },
  label: {
    color: '#ffffff',
    fontSize: 14,
    position: 'absolute',
    bottom: -20,
    left: 0,
    width: 440,
  },
  blurRow: {
    position: 'absolute',
    left: 20,
    flexDirection: 'row',
    gap: 24,
  },
  blurImg: {
    width: 240,
    height: 60,
  },
});
