# Cleansheet

Fire TV (Vega OS) sports app that detects sponsor content in its own video stream with computer vision and replaces or blurs it per viewer, based on chosen categories (gambling, alcohol, custom). Built for the Amazon Developer Hackathon "Build, Ship, Shape": Fire TV track plus the AWS Builder mini challenge.

The full plan, roadmap, and submission checklist live in `fire-tv-sponsor-replacement-plan.md`. Treat it as the source of truth and keep its checkboxes up to date as work lands.

**Deadline:** Oct 23, 2026 @ 12:00pm PDT (3:00pm ET). Favor working, demoable features over completeness.

## Terminology

- **Cleansheet**: the project/app name. (It was previously called "Sidecar".)
- **Sidecar track / sidecar JSON**: the timestamped per-frame metadata (boxes, masks, homographies) the cloud emits alongside the HLS stream. This is a technical term, not the product name. Think "a caption track for ads".

## Architecture

```
CC0 footage + composited fictional sponsors
        -> HLS stream (S3 / CloudFront)
        -> offline worker on the dev Mac: YOLO @ 5-10Hz, tracking, per-board homography -> sidecar JSON
        -> Vega app: KeplerVideoSurfaceView (zIndex 0) + React Native overlay views,
           synced to HTMLMediaElement.currentTime, short playback delay buffer
```

- The device never runs detection. It only renders overlays from the sidecar track.
- Do not re-encode video for the main path. Fallback only if overlay sync is too jittery: swap in cloud-processed segments via Media Source Extensions.
- Replacement methods: blur/pixelate any detection (baseline, also the fallback for low confidence or missed tracks); homography-warped replacement for perimeter boards and banners; blur for jersey sponsors. True inpainting is out of scope.
- Detection: optionally bootstrap with an open-vocabulary detector (Grounding DINO / OWL-ViT), then fine-tune a small YOLO on synthetic composited data.

## Repo layout and commands

- `shared/sidecar/`: the sidecar contract. `schema.json` is the source of truth; `types.ts` and `pipeline/sidecar.py` mirror it, so change all three together. `sync.ts` (`objectsAt`, `filterObjects`) and `homography.ts` (`cssMatrix3d`) are meant to be reused by the Vega app.
- `pipeline/`: Python (run with `.venv/bin/python`; scripts import sibling modules directly). Order: brands → synth_clip (or annotate for real clips) → composite → package_hls.sh.
- `cloud/mock_server.py`: serves `media/` and `assets/` on :8787 with CORS (`--host 0.0.0.0` for the Virtual Device).
- `harness/`: Vite page that plays HLS and draws overlays; the testbed for sync before Vega.
- `app/`: Vega app, not started yet.
- `media/` and footage video files are generated or downloaded and are git-ignored.

```sh
make setup | make synth | make test | make serve | make harness | make clip CLIP=<name>
```

HLS is packaged with B-frames off and timestamps starting at 0 so `currentTime` lines up with sidecar `t`; keep it that way.

## Stack

- **Vega SDK:** 0.24 (CLI 1.4), installed at `~/vega`. Boot the device with `vega virtual-device start -t 300` (the default 60 s timeout is too short for the first boot). If `vega device list` or `run-app` hangs, stop the device, `pkill -f "vda -s emulator"`, and start it again.

- **App:** Vega OS + React Native. Shell forked from `vega-sports-app`; player code borrowed from `vega-video-sample` (MIT-0).
- **Cloud:** no AWS credits. S3 + CloudFront (HLS + sidecar JSON) and Lambda + DynamoDB (per-viewer sponsor-inventory API). Inference runs offline on the Mac (PyTorch MPS); no GPU instances.
- **Test target:** Vega Virtual Device (accepted for submission and judging).
- **Dev tooling:** Amazon Devices Builder Tools MCP:
  `npx -y @amazon-devices/amazon-devices-buildertools-mcp@latest init-context`

## Hard rules

- **No real trademarks or brands anywhere in demo footage, assets, or screenshots.** Use only fictional brands (e.g. "BetNova", "SpinStake") and fictional replacement sponsors.
- **Footage must be CC0 or CC BY** (Pixabay CC0, Wikimedia Commons). Record the license for every clip in the repo. Never use Getty/Pond5 editorial clips, Pexels bulk downloads for training, or SoccerNet video in anything shipped or demoed.
- Cleansheet only filters streams in its own player; it cannot touch other apps (sandboxing, DRM). Don't design features that assume otherwise.
- **AWS costs:** there are no hackathon credits. Use only always-free or near-free services (CloudFront, Lambda, DynamoDB, small S3). Never launch GPU/EC2/SageMaker resources. Ask before creating or deleting cloud resources.
- TV UI must support proper D-pad focus navigation.

## Working conventions

- Pitch and user-facing copy frame the product as **per-viewer sponsor inventory**, not "removing sponsors".
- Keep a running friction log of every Vega SDK / Builder Tools MCP / AWS issue hit (it counts for up to a 10% judging bonus). Add entries as problems come up.
- The riskiest piece is overlay sync with `currentTime`. Prove it on the simulator with hardcoded boxes before building model work on top.
- When the compositing script runs, it should output per-frame ground-truth labels alongside the video; use them for training data and precision/recall numbers.

## Amazon Devices Builder Tools MCP

The `amazon-devices-buildertools-mcp` server (Vega docs search, device tooling) is configured for Claude Code. Its official usage guide, generated by `init-context`, is imported below. Re-running `init-context` appends to this file again, so move any new content back into `.claude/amazon-devices-context.md`.

@.claude/amazon-devices-context.md
