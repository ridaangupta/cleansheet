// Viewer sponsor preferences: which categories this viewer has hidden, and how each hidden
// category is treated. A tiny external store so the overlay and the settings UI (step 5) share it
// without a provider; later loaded from the per-viewer prefs API (Lambda + DynamoDB).

import { useSyncExternalStore } from 'react';

import type { Category } from '@Sidecar';

import { DEFAULT_HIDDEN, DEFAULT_TREATMENTS } from './config';

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

let prefs: ViewerPrefs = { hidden: new Set(DEFAULT_HIDDEN), treatments: { ...DEFAULT_TREATMENTS } };
const listeners = new Set<() => void>();

function update(next: ViewerPrefs): void {
  prefs = next;
  listeners.forEach((l) => l());
}

export function getViewerPrefs(): ViewerPrefs {
  return prefs;
}

export function setCategoryHidden(category: Category, hide: boolean): void {
  const hidden = new Set(prefs.hidden);
  if (hide) hidden.add(category);
  else hidden.delete(category);
  update({ ...prefs, hidden });
}

export function setCategoryTreatment(category: Category, mode: TreatmentMode): void {
  update({ ...prefs, treatments: { ...prefs.treatments, [category]: mode } });
}

export function treatmentFor(p: ViewerPrefs, category: Category): TreatmentMode {
  return p.treatments[category] ?? 'auto';
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useViewerPrefs(): ViewerPrefs {
  return useSyncExternalStore(subscribe, getViewerPrefs);
}
