// Viewer sponsor preferences: which categories this viewer has hidden. A tiny external store so
// the overlay and the settings UI (step 5) share it without a provider; later loaded from the
// per-viewer prefs API (Lambda + DynamoDB).

import { useSyncExternalStore } from 'react';

import type { Category } from '@Sidecar';

export type ViewerPrefs = {
  /** Categories whose boards get treated (replaced, or blurred when low confidence). */
  hidden: ReadonlySet<Category>;
};

let prefs: ViewerPrefs = { hidden: new Set<Category>(['gambling', 'alcohol']) };
const listeners = new Set<() => void>();

export function getViewerPrefs(): ViewerPrefs {
  return prefs;
}

export function setCategoryHidden(category: Category, hide: boolean): void {
  const hidden = new Set(prefs.hidden);
  if (hide) hidden.add(category);
  else hidden.delete(category);
  prefs = { ...prefs, hidden };
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useViewerPrefs(): ViewerPrefs {
  return useSyncExternalStore(subscribe, getViewerPrefs);
}
