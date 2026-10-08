# app/

Vega OS (React Native) app. Empty until the Vega SDK and Virtual Device are installed.

Plan:
1. Fork `vega-sports-app` here for the shell; borrow the player from `vega-video-sample` (MIT-0).
2. Play `http://<host-ip>:8787/media/synth/hls/index.m3u8` (start the mock server with `--host 0.0.0.0`).
3. Port the overlay from `harness/main.ts`: `objectsAt` + `filterObjects` from `shared/sidecar`, driven by `HTMLMediaElement.currentTime`, with RN views layered above `KeplerVideoSurfaceView`.
