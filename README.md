# Cleansheet

Per-viewer sponsor control for Fire TV. Cleansheet detects sponsor boards in a sports stream and replaces or blurs the categories each viewer chooses to hide (gambling, alcohol, or specific brands). A cloud worker publishes a timestamped **sidecar track** of sponsor positions, and the Vega app draws replacements on top of the video in sync with playback.

See `fire-tv-sponsor-replacement-plan.md` for the full plan.

## Layout

| Path | What it is |
| --- | --- |
| `shared/sidecar/` | Sidecar track contract: JSON Schema, TS types, sync (`objectsAt`), homography → CSS `matrix3d` |
| `pipeline/` | Python: fictional brands, synthetic clip, board annotation + tracking, compositing, HLS packaging |
| `cloud/` | `mock_server.py` (local stand-in for S3/CloudFront); the inference worker will live here |
| `harness/` | Browser harness that plays HLS and draws overlays from the sidecar track |
| `app/` | Vega OS app (not started; needs the Vega SDK) |
| `assets/brands/` | Generated fictional sponsor banners + `brands.json` |
| `footage/` | Source clips (git-ignored), `<clip>.boards.json` annotations, `LICENSES.md` |
| `media/` | Generated outputs (git-ignored): composited video, sidecar, dataset, HLS |

## Quick start

Needs Python 3.10+, Node 20+, ffmpeg.

```sh
make setup      # venv + npm install
make synth      # synthetic clip -> composited.mp4, sidecar.json, YOLO dataset, HLS
make test       # vitest, tsc, tracker accuracy vs ground truth
make serve      # terminal 1: http://localhost:8787
make harness    # terminal 2: http://localhost:5173
```

In the harness, toggle categories and treatments, compare the `currentTime` clock (what Vega exposes) against `requestVideoFrameCallback`, and use the offset slider to calibrate skew.

## Real footage

1. Put a CC0/CC BY clip in `footage/` and log it in `footage/LICENSES.md`.
2. `.venv/bin/python pipeline/annotate.py footage/<clip>.mp4`: press `n` and click the 4 corners of each board on a few keyframes, then press `t` to track and `q` to save.
3. `make clip CLIP=<clip>`, then open `http://localhost:5173/?clip=<clip>`.

Known limitation: the compositor pastes over anything in front of a board (players, ball). Clips without occlusion of the boards look best until person masking is added.

## Sidecar track

`shared/sidecar/schema.json` is the source of truth. Each frame has a media time `t` and objects with a stable track `id`, `kind`, `category` (`gambling` | `alcohol` | `neutral`), optional `brand`, a normalized corner `quad` (TL, TR, BR, BL), optional clipped `bbox`, and `confidence`. Validate a file with `.venv/bin/python pipeline/sidecar.py <path>`.

## License

MIT. All brands in `assets/brands/` are fictional.
