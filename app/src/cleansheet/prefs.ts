// Viewer sponsor preferences: which categories this viewer has hidden, and how each hidden
// category is treated. A tiny external store so the overlay and the settings UI share it without a
// provider. Loaded per profile from the sponsor-inventory API (loadViewerPrefs) and saved back to
// it on every change; without the API the defaults from config.ts apply and changes stay local.

import { useSyncExternalStore } from 'react';

import { logWarning } from '@AppUtils/logging';
import type { Category } from '@Sidecar';

import { DEFAULT_HIDDEN, DEFAULT_TREATMENTS, INVENTORY_API } from './config';

/**
 * How a hidden board is treated. 'auto' replaces it when the detection is confident and blurs it
 * otherwise; 'replace' / 'blur' apply one treatment regardless of confidence (a viewer's choice,
 * and how a demo shows the blur while ground-truth sidecars are always fully confident).
 */
export type TreatmentMode = 'auto' | 'replace' | 'blur';

export type ViewerPrefs = {
  /** Categories whose boards get treated. */
  hidden: ReadonlySet<Category>;
  /** Treatment per category; a category not listed is 'auto'. */
  treatments: Readonly<Partial<Record<Category, TreatmentMode>>>;
};

const defaults = (): ViewerPrefs => ({
  hidden: new Set(DEFAULT_HIDDEN),
  treatments: { ...DEFAULT_TREATMENTS },
});

let prefs: ViewerPrefs = defaults();
const listeners = new Set<() => void>();

/** Profile whose prefs are loaded; changes are saved under it. */
let viewerId: string | null = null;
/** Bumped by every local change, so a slow load doesn't overwrite what the viewer just chose. */
let revision = 0;
let saveTimer: ReturnType<typeof setTimeout> | undefined;

/** The API stores only the categories it can hide (see cloud/inventory/handler.py). */
const SAVED_CATEGORIES: readonly Category[] = ['gambling', 'alcohol'];
const SAVE_DELAY_MS = 500;

function update(next: ViewerPrefs): void {
  prefs = next;
  listeners.forEach((l) => l());
}

function prefsUrl(id: string): string {
  return `${INVENTORY_API}/viewers/${encodeURIComponent(id)}/prefs`;
}

/**
 * Load a profile's saved prefs (or the defaults if it has none). Call when the profile is known;
 * later changes are saved under it. Failures keep the current prefs.
 */
export async function loadViewerPrefs(id: string): Promise<void> {
  if (id !== viewerId) {
    viewerId = id;
    update(defaults());
  }
  const startedAt = revision;
  try {
    const res = await fetch(prefsUrl(id));
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const body = (await res.json()) as {
      hidden: Category[];
      treatments: Partial<Record<Category, TreatmentMode>>;
      saved: boolean;
    };
    if (viewerId !== id || revision !== startedAt) return; // profile switched or viewer changed something
    // An unsaved profile gets config.ts's defaults (which may set demo treatments), not the API's.
    if (body.saved)
      update({ hidden: new Set(body.hidden), treatments: body.treatments });
  } catch (e) {
    logWarning(`[cleansheet] loading prefs for ${id} failed: ${String(e)}`);
  }
}

function changed(next: ViewerPrefs): void {
  revision += 1;
  update(next);
  const id = viewerId;
  if (!id) return;
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    const body = {
      hidden: [...next.hidden].filter((c) => SAVED_CATEGORIES.includes(c)),
      treatments: Object.fromEntries(
        Object.entries(next.treatments).filter(([c]) =>
          SAVED_CATEGORIES.includes(c as Category),
        ),
      ),
    };
    fetch(prefsUrl(id), {
      method: 'PUT',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    })
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
      })
      .catch((e: unknown) =>
        logWarning(`[cleansheet] saving prefs for ${id} failed: ${String(e)}`),
      );
  }, SAVE_DELAY_MS);
}

export function getViewerPrefs(): ViewerPrefs {
  return prefs;
}

export function setCategoryHidden(category: Category, hide: boolean): void {
  const hidden = new Set(prefs.hidden);
  if (hide) hidden.add(category);
  else hidden.delete(category);
  changed({ ...prefs, hidden });
}

export function setCategoryTreatment(
  category: Category,
  mode: TreatmentMode,
): void {
  changed({ ...prefs, treatments: { ...prefs.treatments, [category]: mode } });
}

export function treatmentFor(
  p: ViewerPrefs,
  category: Category,
): TreatmentMode {
  return p.treatments[category] ?? 'auto';
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useViewerPrefs(): ViewerPrefs {
  return useSyncExternalStore(subscribe, getViewerPrefs);
}
