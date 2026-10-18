# Cleansheet

Per-viewer sponsor control for Fire TV. Cleansheet detects sponsor boards in a sports stream and replaces or obscures the categories each viewer chooses to hide (gambling, alcohol, or specific brands). A cloud worker publishes a timestamped **sidecar track** of sponsor positions, and the Vega app draws replacements on top of the video in sync with playback.

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

The current real clips (`tachira_01` to `tachira_04`) come from a public-domain VTV broadcast on Wikimedia Commons; `footage/tachira.sh` downloads it and cuts them. To add more:

1. Find a CC0 / CC BY / public-domain broadcast, then `.venv/bin/python pipeline/find_shots.py <broadcast>` to list uncut wide-camera stretches (`media/shots/<name>/contact.jpg`).
2. `.venv/bin/python pipeline/cut_clip.py <broadcast> <start s> 12 footage/<clip>.mp4 --mask x,y,w,h ...` to cut a clip and pixelate fixed graphics (scorebug, channel logo). Log it in `footage/LICENSES.md`.
3. `.venv/bin/python pipeline/annotate.py footage/<clip>.mp4`: press `n` and click 4 corners (TL, TR, BR, BL). For a straight run of perimeter boards, annotate the whole row as one quad anchored on board seams, then `+`/`-` to split it into boards and `[`/`]` to extend it past the clicked part. Press `t` to track, `q` to save. The grey margin around the frame is clickable.
4. `make clip CLIP=<clip>`, then open `http://localhost:5173/?clip=<clip>`. Check the composite for real brands showing through before using it anywhere.

Known limitation: the compositor pastes over anything in front of a board (players, ball). Clips without occlusion of the boards look best until person masking is added.

## Sidecar track

`shared/sidecar/schema.json` is the source of truth. Each frame has a media time `t` and objects with a stable track `id`, `kind`, `category` (`gambling` | `alcohol` | `neutral`), optional `brand`, a normalized corner `quad` (TL, TR, BR, BL), optional clipped `bbox`, and `confidence`. Validate a file with `.venv/bin/python pipeline/sidecar.py <path>`.

## License

- `pipeline/` is AGPL-3.0 (`pipeline/LICENSE`): the detector training, inference and person masking use [Ultralytics YOLO](https://github.com/ultralytics/ultralytics), which is AGPL-3.0, and so would any weights trained with it.
- Everything else (the Vega app, `shared/`, `cloud/`, `harness/`, assets) is MIT (`LICENSE`). None of it imports Ultralytics. `app/` is forked from Amazon's `vega-sports-app` (MIT-0, `app/LICENSE`).
- All brands in `assets/brands/` are fictional. Footage licenses are in `footage/LICENSES.md`.
