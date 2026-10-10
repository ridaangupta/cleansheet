# app/

Vega OS (React Native 0.83) app. Forked from [vega-sports-app](https://github.com/AmazonAppDev/vega-sports-app) at `bf51e7d` (MIT-0, see `LICENSE`); the upstream README is in `docs/UPSTREAM_README.md`.

Changes from upstream so far:
- `src/cleansheet/`: our code. `SponsorOverlay.tsx` looks up the sidecar from `currentTime` (mounted in `src/services/videoPlayer/components/VideoPlayer/VideoPlayer.tsx`); `SponsorTreatments.tsx` warps a replacement sponsor (or, below `REPLACE_MIN_CONFIDENCE`, the board's blurred texture) onto every board in a hidden category; `SponsorSettingsPanel.tsx` is the viewer's settings over the player (Sponsors button in the control bar, D-pad navigable); `prefs.ts` holds the viewer's hidden categories and a treatment per category (`auto` = replace when confident, else blur; or always `replace` / `blur`); `config.ts` holds the media server URL, the sync offset, viewer defaults (`DEFAULT_HIDDEN`, `DEFAULT_TREATMENTS`) and dev switches (`SYNC_TEST`, `SHOW_BOXES`, `SHOW_STATS`, `SYNC_LOG`). Ground-truth sidecars are always fully confident, so `auto` only replaces: set a category to `blur` to show the blurred texture (demo: gambling replaced, alcohol blurred).
- `shared/sidecar` is imported as `@Sidecar` (alias in `babel.config.js` and `tsconfig.json`; `metro.config.js` watches `../shared` and resolves its deps from `app/node_modules`).
- The first live stream (`src/api/liveStreams/staticData/liveStreamDetails.json`) and the player fallback (`EXAMPLE_VIDEO` in `src/screens/VideoPlayerScreen/VideoPlayerScreen.tsx`) play `http://10.0.2.2:8787/media/synth/hls/index.m3u8`. `10.0.2.2` is the host Mac as seen from the Vega Virtual Device.
- `lefthook` removed so the sample's git hooks don't get installed into the Cleansheet repo.
- Catalogue images (static JSON, seek-bar placeholder) come from `assets/ui/` on the mock server (`pipeline/ui_art.py`), not the sample's CDN, whose images show real brands; the app icon is Cleansheet's.

## Build and run

Needs Java 21+ for the Shaka Player build (Homebrew `openjdk@21`) and Node 22+.

```sh
export JAVA_HOME=/opt/homebrew/opt/openjdk@21 PATH="$JAVA_HOME/bin:$HOME/vega/bin:$PATH"
npm install                    # also clones, patches, and builds Shaka Player into src/w3cmedia/
npm run build:debug            # -> build/aarch64-debug/keplersportapp_aarch64.vpkg (VVD on Apple Silicon)
make -C .. serve               # mock CDN on :8787 (separate terminal)
vega virtual-device start -t 300
vega device list               # wait until the device shows up before installing
vega run-app build/aarch64-debug/keplersportapp_aarch64.vpkg
```

Login: debug builds sign in automatically when `app/.env` (git-ignored) sets `REACT_APP_DEV_AUTO_SIGN_IN_EMAIL` and `REACT_APP_DEV_AUTO_SIGN_IN_PASSWORD`; any values work against the static auth data. See `.env.example`.

To reach the synthetic clip after launch: Enter (pick profile), Enter (open the focused live stream), Enter (play). From a script:

```sh
vega exec vda -s emulator-5554 shell "inputd-cli button_press KEY_ENTER"
```

The Vega screenshot tool doesn't work on the VVD; use `scripts/vvd_screenshot.sh out.png` from the repo root (captures only the VVD window, which must be on screen). The mock server's request log also shows whether segments are being fetched.

## Sync test

With `SYNC_TEST = true` in `src/cleansheet/config.ts`, every stream plays `media/<clip>/hls_tc` (built by `make synctest`), which has the frame number burned in at the top right. The overlay HUD at the top left shows the frame it is drawing. Screenshot during playback; HUD minus burned-in number is the sync error in frames. `SYNC_OFFSET_S` corrects the constant part (0.117 s on the VVD). Set `SYNC_TEST = false` to play the normal streams.
