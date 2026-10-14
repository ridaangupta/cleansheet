// Sponsor overlay over the video, driven by the player's currentTime: looks up the sidecar track
// (snapped for per-frame tracks), renders the viewer's treatments (SponsorTreatments), and optionally
// debug boxes and the sync HUD. Port of the currentTime path in harness/main.ts.

import React, { useEffect, useRef, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { useAuth } from '@AppServices/auth';

import {
  objectsAt,
  parseSidecar,
  samplesVideoFrames,
  visibleBBox,
  type SidecarFile,
  type SidecarObject,
  type SidecarTrack,
} from '@Sidecar';

import {
  SHOW_BOXES,
  SHOW_STATS,
  SIDECAR_URL,
  SYNC_LOG,
  SYNC_OFFSET_S,
  SYNC_TEST,
} from './config';
import { loadViewerPrefs } from './prefs';
import { SponsorTreatments } from './SponsorTreatments';

type Props = {
  /** Current media time in seconds, or undefined while the player isn't ready. */
  getTime: () => number | undefined;
  width: number;
  height: number;
};

type Snapshot = { time: number; objects: SidecarObject[] };

const CATEGORY_COLORS: Record<SidecarObject['category'], string> = {
  gambling: '#ff3b30',
  alcohol: '#ffcc00',
  neutral: '#34c759',
};

export const SponsorOverlay = ({ getTime, width, height }: Props) => {
  const [track, setTrack] = useState<SidecarTrack | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState<Snapshot>({
    time: NaN,
    objects: [],
  });
  // Loop rate (animation frames/s) and update rate (React state changes/s), to see whether the
  // JS thread keeps up with the video.
  const rates = useRef({
    loops: 0,
    updates: 0,
    since: 0,
    loopHz: 0,
    updateHz: 0,
  });
  const { user } = useAuth();

  // This profile's saved sponsor prefs (the settings panel saves changes back).
  useEffect(() => {
    if (user?.id) void loadViewerPrefs(user.id);
  }, [user?.id]);

  useEffect(() => {
    let cancelled = false;
    fetch(SIDECAR_URL)
      .then((res) => {
        if (!res.ok) throw new Error(`${res.status} fetching ${SIDECAR_URL}`);
        return res.json() as Promise<SidecarFile>;
      })
      .then((f) => !cancelled && setTrack(parseSidecar(f)))
      .catch((e: unknown) => !cancelled && setError(String(e)));
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!track) return;
    // A per-frame ground-truth track snaps to the frame on screen; a sparse model track interpolates.
    const snap = samplesVideoFrames(track);
    let raf = 0;
    let last: SidecarObject[] = [];
    let lastAt = 0;
    const loop = (now: number) => {
      const r = rates.current;
      r.loops += 1;
      const t = getTime();
      if (t !== undefined && !Number.isNaN(t)) {
        const objects = objectsAt(track, t, {
          offset: SYNC_OFFSET_S,
          interpolate: !snap,
        });
        // Re-render only when there is something new to draw: snapped lookups return the same
        // array until the sidecar frame changes; interpolated ones are capped at ~30 updates/s.
        const changed = snap
          ? objects !== last && !(objects.length === 0 && last.length === 0)
          : now - lastAt >= 33;
        if (changed) {
          last = objects;
          lastAt = now;
          r.updates += 1;
          if (SYNC_LOG) console.log(`[cleansheet-sync] ${t.toFixed(4)}`);
          setSnapshot({ time: t, objects });
        }
      }
      if (now - r.since >= 1000) {
        r.loopHz = (r.loops * 1000) / (now - r.since);
        r.updateHz = (r.updates * 1000) / (now - r.since);
        r.loops = 0;
        r.updates = 0;
        r.since = now;
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [track, getTime]);

  // Where the video pixels land inside the player (contain fit).
  const vw = track?.width ?? 16;
  const vh = track?.height ?? 9;
  const scale = Math.min(width / vw, height / vh);
  const rect = {
    x: (width - vw * scale) / 2,
    y: (height - vh * scale) / 2,
    w: vw * scale,
    h: vh * scale,
  };
  // The frame the overlay is drawing, i.e. after the sync offset.
  // + 1 ms matches the snapped lookup in objectsAt at frame boundaries.
  const frame = track
    ? Math.floor((snapshot.time + SYNC_OFFSET_S + 1e-3) * track.fps)
    : NaN;

  return (
    <View
      pointerEvents="none"
      style={[
        styles.layer,
        { left: rect.x, top: rect.y, width: rect.w, height: rect.h },
      ]}>
      <SponsorTreatments
        objects={snapshot.objects}
        width={rect.w}
        height={rect.h}
      />
      {SHOW_BOXES &&
        snapshot.objects.map((o) => {
          const [x, y, w, h] = visibleBBox(o.quad);
          return (
            <View
              key={o.id}
              style={[
                styles.box,
                {
                  left: x * rect.w,
                  top: y * rect.h,
                  width: w * rect.w,
                  height: h * rect.h,
                  borderColor: CATEGORY_COLORS[o.category],
                },
              ]}>
              <Text
                style={[styles.label, { color: CATEGORY_COLORS[o.category] }]}
                numberOfLines={1}>
                {o.brand ?? o.id}
              </Text>
            </View>
          );
        })}
      {(SYNC_TEST || SHOW_STATS) && (
        <View style={styles.hud}>
          <Text style={styles.hudFrame}>
            {Number.isNaN(frame)
              ? 'F----'
              : `F${String(frame).padStart(4, '0')}`}
          </Text>
          <Text style={styles.hudText}>
            {error ??
              `t ${Number.isNaN(snapshot.time) ? '-' : snapshot.time.toFixed(3)}s  ·  ${snapshot.objects.length} obj  ·  loop ${rates.current.loopHz.toFixed(0)}/s  ·  updates ${rates.current.updateHz.toFixed(0)}/s`}
          </Text>
        </View>
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  layer: {
    position: 'absolute',
    overflow: 'hidden',
    zIndex: 1,
  },
  box: {
    position: 'absolute',
    borderWidth: 3,
  },
  label: {
    position: 'absolute',
    top: -26,
    left: 0,
    fontSize: 18,
    fontWeight: 'bold',
  },
  // Top-left, mirroring the burned-in counter in the top-right of the test clip.
  hud: {
    position: 'absolute',
    top: 15,
    left: 15,
    paddingHorizontal: 12,
    paddingVertical: 6,
    backgroundColor: 'rgba(0,0,0,0.85)',
  },
  hudFrame: {
    color: '#00e5ff',
    fontSize: 64,
    fontWeight: 'bold',
    fontVariant: ['tabular-nums'],
  },
  hudText: {
    color: '#ffffff',
    fontSize: 18,
  },
});
