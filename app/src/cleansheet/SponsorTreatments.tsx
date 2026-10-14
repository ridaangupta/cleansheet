// Per-viewer sponsor treatments over the video. For every board in a category the viewer hides:
//  - replace: a fictional replacement sponsor warped onto the board (homography via matrix4), the
//    one the sponsor-inventory API assigns to that board slot;
//  - blur: when the detection is low confidence, the board's own cloud-made blurred texture
//    (pipeline/board_textures.py), warped the same way. Vega can't blur the video itself.
// One Image per treated board; each is memoized and recomputes its matrix once per sidecar frame.

import React, { memo, useEffect, useMemo, useState } from 'react';
import { Image, StyleSheet } from 'react-native';

import { logWarning } from '@AppUtils/logging';
import {
  filterObjects,
  growQuad,
  isConvexQuad,
  matrix4,
  type Quad,
  type SidecarObject,
} from '@Sidecar';

import {
  BRANDS_URL,
  CLIP,
  INVENTORY_API,
  MEDIA_SERVER,
  REPLACE_MIN_CONFIDENCE,
  TEXTURES_URL,
} from './config';
import { treatmentFor, useViewerPrefs } from './prefs';

type Props = { objects: SidecarObject[]; width: number; height: number };

type Brand = { name: string; category: string; file: string };
type TextureIndex = Record<string, { w: number; h: number }>;
type Replacement = { uri: string; size: [number, number] };
type Assets = {
  replacements: Replacement[];
  /** Board id -> its slot's replacement sponsor, from the inventory API. */
  slots: Record<string, Replacement>;
  /** Board id -> blurred texture size, built once so Warped's memo sees the same tuple. */
  textures: Record<string, [number, number]>;
};

/** Screen px the warped image extends past the board on every side, so real edges don't show. */
const GROW_PX = 1.5;

// Fallback replacement per board when the inventory API has no slot for it (or is unreachable).
function hashIndex(id: string, n: number): number {
  let h = 2166136261;
  for (let i = 0; i < id.length; i++)
    h = Math.imul(h ^ id.charCodeAt(i), 16777619);
  return Math.abs(h) % n;
}

type WarpedProps = {
  uri: string;
  size: [number, number];
  quad: Quad;
  width: number;
  height: number;
};

// With a snapped sidecar, `quad` is the same array object until its frame changes.
const Warped = memo(({ uri, size, quad, width, height }: WarpedProps) => {
  const matrix = useMemo(() => {
    const px = quad.map(([x, y]) => [x * width, y * height]) as Quad;
    return matrix4(size[0], size[1], growQuad(px, GROW_PX));
  }, [size, quad, width, height]);
  return (
    <Image
      source={{ uri }}
      style={[
        styles.warped,
        { width: size[0], height: size[1], transform: [{ matrix }] },
      ]}
    />
  );
});

function useAssets(): Assets | null {
  const [assets, setAssets] = useState<Assets | null>(null);
  useEffect(() => {
    let cancelled = false;
    Promise.all([
      fetch(BRANDS_URL).then(
        (r) => r.json() as Promise<{ size: [number, number]; brands: Brand[] }>,
      ),
      // A clip without textures still gets replacements; low-confidence boards are then left alone.
      fetch(`${TEXTURES_URL}/index.json`)
        .then((r): Promise<TextureIndex> | TextureIndex =>
          r.ok ? (r.json() as Promise<TextureIndex>) : {},
        )
        .catch((): TextureIndex => ({})),
      // Without the API every board still gets a stable replacement (hashIndex).
      fetch(`${INVENTORY_API}/videos/${CLIP}/inventory`)
        .then((r) =>
          r.ok
            ? (r.json() as Promise<{ slots: Record<string, string> }>)
            : { slots: {} },
        )
        .catch((e: unknown) => {
          logWarning(`[cleansheet] inventory for ${CLIP} failed: ${String(e)}`);
          return { slots: {} as Record<string, string> };
        }),
    ])
      .then(([brands, index, inventory]) => {
        if (cancelled) return;
        const byName = new Map(
          brands.brands
            .filter((b) => b.category === 'replacement')
            .map(
              (b) =>
                [
                  b.name,
                  {
                    uri: `${MEDIA_SERVER}/assets/brands/${b.file}`,
                    size: brands.size,
                  },
                ] as const,
            ),
        );
        const slots: Record<string, Replacement> = {};
        for (const [id, sponsor] of Object.entries(inventory.slots)) {
          const r = byName.get(sponsor);
          if (r) slots[id] = r;
        }
        setAssets({
          replacements: [...byName.values()],
          slots,
          textures: Object.fromEntries(
            Object.entries(index).map(([id, t]) => [id, [t.w, t.h]]),
          ),
        });
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);
  return assets;
}

export const SponsorTreatments = ({ objects, width, height }: Props) => {
  const assets = useAssets();
  const prefs = useViewerPrefs();
  // A non-convex quad would warp the image across the screen: skip it rather than draw it.
  const treated = useMemo(
    () =>
      filterObjects(objects, { categories: prefs.hidden }).filter((o) =>
        isConvexQuad(o.quad),
      ),
    [objects, prefs.hidden],
  );
  if (!assets || assets.replacements.length === 0) return null;

  return (
    <>
      {treated.map((o) => {
        const mode = treatmentFor(prefs, o.category);
        const blur =
          mode === 'blur' ||
          (mode === 'auto' && o.confidence < REPLACE_MIN_CONFIDENCE);
        if (blur) {
          const size = assets.textures[o.id];
          if (!size) return null;
          return (
            <Warped
              key={`b-${o.id}`}
              uri={`${TEXTURES_URL}/blur/${o.id}.png`}
              size={size}
              quad={o.quad}
              width={width}
              height={height}
            />
          );
        }
        const r =
          assets.slots[o.id] ??
          assets.replacements[hashIndex(o.id, assets.replacements.length)]!;
        return (
          <Warped
            key={`r-${o.id}`}
            uri={r.uri}
            size={r.size}
            quad={o.quad}
            width={width}
            height={height}
          />
        );
      })}
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
});
