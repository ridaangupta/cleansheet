// Per-viewer sponsor inventory settings, over the player. One row per category with four
// options: Show (not hidden), or hidden with Auto / Replace / Blur. Changes apply live through
// prefs.ts, so the boards switch while the match keeps playing.
//
// Focus (Vega guidance): trapped inside the panel, initial focus on the first row's current
// choice, physical focus indicator (border + scale), Back or Done closes and the caller restores
// focus to the button that opened it.

import React, { useEffect, useState } from 'react';
import { BackHandler, Pressable, StyleSheet, Text, View } from 'react-native';

import { TVFocusGuideView } from '@amazon-devices/react-native-kepler';

import type { Category } from '@Sidecar';

import { setCategoryHidden, setCategoryTreatment, treatmentFor, useViewerPrefs, type TreatmentMode } from './prefs';

type Choice = 'show' | TreatmentMode;

const CATEGORIES: { id: Category; label: string }[] = [
  { id: 'gambling', label: 'Gambling' },
  { id: 'alcohol', label: 'Alcohol' },
];

const CHOICES: { id: Choice; label: string }[] = [
  { id: 'show', label: 'Show' },
  { id: 'auto', label: 'Auto' },
  { id: 'replace', label: 'Replace' },
  { id: 'blur', label: 'Blur' },
];

function choose(category: Category, choice: Choice): void {
  if (choice === 'show') {
    setCategoryHidden(category, false);
    return;
  }
  setCategoryTreatment(category, choice);
  setCategoryHidden(category, true);
}

type OptionProps = {
  label: string;
  selected: boolean;
  preferred: boolean;
  onPress: () => void;
  testID: string;
};

const Option = ({ label, selected, preferred, onPress, testID }: OptionProps) => {
  const [focused, setFocused] = useState(false);
  return (
    <Pressable
      testID={testID}
      role="radio"
      aria-checked={selected}
      aria-label={label}
      hasTVPreferredFocus={preferred}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
      onPress={onPress}
      style={[styles.option, selected && styles.optionSelected, focused && styles.optionFocused]}>
      <Text style={[styles.optionText, selected && styles.optionTextSelected]}>{label}</Text>
    </Pressable>
  );
};

type Props = { onClose: () => void };

export const SponsorSettingsPanel = ({ onClose }: Props) => {
  const prefs = useViewerPrefs();
  const [doneFocused, setDoneFocused] = useState(false);

  // Back closes the panel instead of leaving the player (latest listener runs first).
  useEffect(() => {
    const sub = BackHandler.addEventListener('hardwareBackPress', () => {
      onClose();
      return true;
    });
    return () => sub.remove();
  }, [onClose]);

  const current = (c: Category): Choice => (prefs.hidden.has(c) ? treatmentFor(prefs, c) : 'show');

  return (
    <View style={styles.panel} testID="sponsor-settings-panel">
      <TVFocusGuideView autoFocus trapFocusUp trapFocusDown trapFocusLeft trapFocusRight>
        <Text style={styles.title}>Sponsor inventory</Text>
        <Text style={styles.subtitle}>Choose which sponsors this viewer sees. Changes apply live.</Text>
        {CATEGORIES.map((cat, row) => (
          <View key={cat.id} style={styles.row}>
            <Text style={styles.rowLabel}>{cat.label}</Text>
            <View style={styles.options} role="radiogroup" aria-label={`${cat.label} sponsors`}>
              {CHOICES.map((ch) => (
                <Option
                  key={ch.id}
                  testID={`sponsor-${cat.id}-${ch.id}`}
                  label={ch.label}
                  selected={current(cat.id) === ch.id}
                  preferred={row === 0 && current(cat.id) === ch.id}
                  onPress={() => choose(cat.id, ch.id)}
                />
              ))}
            </View>
          </View>
        ))}
        <Text style={styles.hint}>
          Replace: a family sponsor. Blur: hide the board. Auto: replace when confident, else blur.
        </Text>
        <Pressable
          testID="sponsor-settings-done"
          role="button"
          aria-label="Done"
          onFocus={() => setDoneFocused(true)}
          onBlur={() => setDoneFocused(false)}
          onPress={onClose}
          style={[styles.done, doneFocused && styles.optionFocused]}>
          <Text style={styles.doneText}>Done</Text>
        </Pressable>
      </TVFocusGuideView>
    </View>
  );
};

const ACCENT = '#2f7df6';

// The app lays out at 960x540. The panel sits bottom-left, clear of the top of the picture where
// perimeter boards run in a broadcast wide shot, so the viewer sees the boards change live.
const styles = StyleSheet.create({
  panel: {
    position: 'absolute',
    left: 24,
    bottom: 64,
    width: 436,
    paddingHorizontal: 18,
    paddingVertical: 14,
    borderRadius: 10,
    backgroundColor: 'rgba(12, 14, 20, 0.9)',
    zIndex: 10,
  },
  title: { color: '#ffffff', fontSize: 18, fontWeight: '700' },
  subtitle: { color: '#c9ccd3', fontSize: 11, marginTop: 2, marginBottom: 4 },
  row: { marginTop: 8 },
  rowLabel: { color: '#ffffff', fontSize: 13, fontWeight: '600', marginBottom: 6 },
  options: { flexDirection: 'row', gap: 10 },
  // Fixed widths and gaps larger than the focused scale's growth, so focus never overlaps a neighbour.
  option: {
    width: 92,
    height: 32,
    borderRadius: 6,
    borderWidth: 2,
    borderColor: 'transparent',
    backgroundColor: 'rgba(255, 255, 255, 0.12)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  optionSelected: { backgroundColor: ACCENT },
  optionFocused: { borderColor: '#ffffff', transform: [{ scale: 1.06 }] },
  optionText: { color: '#e8eaee', fontSize: 13 },
  optionTextSelected: { color: '#ffffff', fontWeight: '700' },
  hint: { color: '#9aa0aa', fontSize: 10.5, marginTop: 10, lineHeight: 14 },
  done: {
    marginTop: 10,
    alignSelf: 'flex-start',
    paddingHorizontal: 22,
    height: 32,
    borderRadius: 6,
    borderWidth: 2,
    borderColor: 'transparent',
    backgroundColor: 'rgba(255, 255, 255, 0.18)',
    justifyContent: 'center',
  },
  doneText: { color: '#ffffff', fontSize: 13, fontWeight: '600' },
});
