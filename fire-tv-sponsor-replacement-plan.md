# Cleansheet: Per-Viewer Sponsor Control for Fire TV

**Hackathon:** Build, Ship, Shape: Amazon Developer Hackathon
**Primary track:** Fire TV (Vega OS)
**Mini challenge:** AWS Builder
**Deadline:** Oct 23, 2026 @ 12:00pm PDT (3:00pm ET)
**Judging:** Nov 9 to 20, 2026

*"Cleansheet" is the project name (formerly "Sidecar"). "Sidecar" below refers only to the timestamped metadata track.*

---

## 1. The Idea

Sports broadcasts are saturated with gambling sponsorships: perimeter boards, jersey sponsors, and commercial breaks. Many viewers want them gone: Muslim viewers for whom gambling is haram, people in gambling addiction recovery (betting ads are a genuine relapse trigger), and parents filtering gambling and alcohol content for kids.

Cleansheet is a Fire TV sports app that detects sponsor content in the video stream using computer vision and **replaces or obscures it in real time based on each viewer's chosen categories** (gambling, alcohol, custom).

### Pitch framing

Do not pitch it as "removing sponsors." For leagues and streamers, that sounds like lost revenue. Pitch it as **per-viewer sponsor inventory**: the same board can show a betting brand to one viewer and a family-safe or halal-friendly sponsor to another. Leagues sell each slot twice, and viewers get control. Broadcasters already swap perimeter boards by region using virtual advertising; Cleansheet moves that capability to the individual viewer.

This matters for the panel, which includes an NBA product manager, the founding partner of Vega OS (Callstack), and Fire TV leadership.

### Priority categories hit

Sports, AI-enhanced viewing, computer vision.

---

## 2. Hard Constraints

| Constraint | Implication |
| --- | --- |
| Fire TV apps are sandboxed and DRM surfaces block capture | Cannot filter other apps (ESPN, DAZN, Prime). Cleansheet processes streams in **its own player**. Frame it as what a streaming service or league could ship. |
| Hackathon rules: no third-party trademarks or copyrighted footage without permission | Real betting logos cannot appear in the demo video, even in licensed footage. |
| Fire TV hardware cannot run detection at 30fps | Vision runs off-device; the device only renders overlays. |
| No hackathon AWS credits available | Run detection offline on the dev Mac (the demo streams are VOD, so sidecar tracks can be precomputed). Use AWS only for services that are always-free or cost cents: CloudFront, Lambda, DynamoDB, plus S3 for a few hundred MB. |
| Editorial stock licenses typically prohibit altering footage | Avoid Getty/Pond5 editorial clips. |
| SoccerNet broadcast video requires an NDA and is research-only | OK for private experiments, never in the demo. |
| Pexels prohibits bulk API collection for ML training | Use CC0 sources for anything that goes into training. |

---

## 3. Footage Strategy

1. Source 3 to 5 **CC0 or CC BY** clips of amateur or lower-league matches (Pixabay CC0, Wikimedia Commons). Keep license records for every clip.
2. Invent fictional betting brands (e.g. "BetNova", "SpinStake") and fictional replacement sponsors.
3. **Composite the fake brands** onto boards and jerseys with a script before the stream reaches the app.

Benefits:
- Zero trademark risk in the demo.
- **Free ground-truth labels** for every frame, giving a synthetic training set and real precision/recall numbers.
- Controlled difficulty: show occlusion, motion blur, and camera pans honestly.

---

## 4. Architecture

```
CC0 footage + composited fake sponsors
            │
            ▼
   HLS stream (S3 / CloudFront)
            │
   ┌────────┴──────────────────────────┐
   ▼                                   ▼
Offline worker (dev Mac)         Vega app (Fire TV)
- YOLO detection @ 5-10Hz        - KeplerVideoSurfaceView (zIndex 0)
- tracking between detections    - React Native overlay views above
- homography per board           - synced to HTMLMediaElement.currentTime
- emits timestamped sidecar      - category toggles (gambling, alcohol, custom)
  JSON ("a caption track          - short playback delay buffer
  for ads")
   └──────────────► sidecar track ─┘
```

### Key design decisions

- **Sidecar metadata, not re-encoded video.** The cloud emits per-frame boxes, masks, and homographies with timestamps. The device draws replacements on top. Low bandwidth, low latency, no video re-encode.
- **Vega overlay model.** Vega's W3C Media API renders video via `KeplerVideoSurfaceView` in the React Native tree, so replacements are ordinary RN views layered above it.
- **Fallback:** Vega supports Media Source Extensions. If overlay sync is too jittery, swap in cloud-processed segments via MSE instead.
- **Detection:** Bootstrap with an open-vocabulary detector (Grounding DINO or OWL-ViT) if needed, then fine-tune a small YOLO model on the synthetic data for speed.

### Replacement difficulty ladder

| Target | Method | Status |
| --- | --- | --- |
| Low-confidence detection | Obscure (method open: per-board blurred texture or mosaic; see Next up step 3) | Open problem: Vega can't blur video from an overlay |
| Perimeter boards, banners | Homography warp of replacement sponsor | Core feature |
| Jersey sponsors | None: illegible at wide-shot size, and Vega can't blur video | Proposed out of scope |
| True inpainting | Too slow for real time | Out of scope |
| Commentator sponsor reads | ASR on audio, mute segments | Stretch |
| Gambling commercials in breaks | Classify and swap | Stretch |

### Stack

- **App:** Vega OS, React Native. Fork `vega-sports-app` for the shell, borrow player code from `vega-video-sample` (MIT-0).
- **Dev tooling:** Amazon Devices Builder Tools MCP in Claude Code:
  `npx -y @amazon-devices/amazon-devices-buildertools-mcp@latest init-context`
- **Cloud (AWS Builder, no credits):** S3 + CloudFront serve the HLS stream and the sidecar JSON. Lambda + DynamoDB (always-free tiers) serve the per-viewer sponsor-inventory API: viewer category preferences and which replacement sponsor fills each slot. Inference runs offline on the dev Mac (PyTorch MPS) because the demo clips are VOD; a live version would move the same worker to a GPU instance.
- **Test target:** Vega Virtual Device (simulator is accepted for submission and judging).

---

## 5. Roadmap

### Week 1: Oct 8 to 14 (de-risk)

- [x] ~~Request $150 AWS credits~~ (credits no longer available; see the no-credits cloud plan in section 4).
- [x] Set up Vega SDK, Vega Virtual Device, Builder Tools MCP.
- [x] Fork the sports sample; get a local HLS clip playing on the simulator.
- [x] Source 3 to 5 CC0 match clips; log licenses.
  - Done 2026-10-09: four 12 s clips (`footage/tachira_01..04.mp4`) from VTV's public-domain ({{PD-VenezuelaGov}}) broadcast of Deportivo Táchira vs. Rayo Zuliano on Wikimedia Commons, logged in `footage/LICENSES.md` and rebuildable with `footage/tachira.sh`. Picked with `pipeline/find_shots.py` (uncut wide-camera stretches), cut with `pipeline/cut_clip.py` (720p30, audio dropped, scorebug and VTV logo pixelated). Pixabay was ruled out: its license hasn't been CC0 since 2019.
  - The clips still show real sponsors on the boards (including two real betting brands) until they are annotated and composited. Don't use them uncomposited in anything shown.
- [x] Design fictional brands; build the compositing script that outputs video + per-frame labels.
- [x] **Prove overlay sync** on the simulator with hardcoded boxes driven by `currentTime`. This is the riskiest piece; solve it before touching the model.
  - Done 2026-10-08 on the Vega Virtual Device with ground-truth sidecar boxes (`app/src/cleansheet/SponsorOverlay.tsx`). Measured with burned-in frame numbers (`make synctest`): `currentTime` trails the displayed frame by a constant 3 frames (100 ms); with `SYNC_OFFSET_S = 0.1` the error is 0 to 1 frame (10 samples, one 2-frame sample right after start). The overlay loop runs at 120 to 220 fps, so the JS thread keeps up. Re-measure on real hardware if we get one. Re-measured 2026-10-09 on `tachira_02` after switching the per-frame sidecar to snapped lookups and rendering only on new sidecar frames: offset raised to 0.117 s; 8 of 12 samples on the displayed frame, the rest 1 off; 29-30 renders/s. On-device render log: `currentTime` advances in 33 ms (one-frame) steps, so interpolating the per-frame track would sit a fixed ~0.95 frame ahead (2.3 px mean, 11.4 px max over the logged 2.2 s; ~20 px in the fastest pan); snapped lookups remove that.
- [ ] Replace the sports sample's images (hero, thumbnails, profiles load from the sample's CDN). The home hero shows real Adidas logos, which breaks the no-real-brands rule for demo footage and screenshots.
- [x] Start the friction log on day one.

### Next up (written 2026-10-09)

Ordered; each step lists who does it. "You" = steps that need a person at the Mac (interactive windows, accounts, judgment calls).

1. ~~**Annotate the board rows on the four real clips**~~ Done 2026-10-09 by Claude (rows + camera-motion tracking + correction keyframes; `footage/tachira_0N.boards.json`). Needs your review of the four composites. Original instructions kept for future clips: `.venv/bin/python pipeline/annotate.py footage/tachira_0N.mp4`; one row quad per straight run of boards (top row and LED band on the far side, plus any row behind a goal line that comes into view), anchored on board seams; `+`/`-` to split, `[`/`]` to extend, `t` to track. `footage/tachira_02.boards.json` is a rough draft to start from. Then `make clip CLIP=tachira_0N` and scrub `media/tachira_0N/composited.mp4` for real brands showing through.
2. ~~**Make composites look broadcast-real**~~ Done 2026-10-09: `composite.py` measures the real boards on sample frames and tone-matches each fake board (brightness, contrast, saturation, clamped so brands stay legible), adds seams, blurs to the footage's measured sharpness (1.0-1.5 px vs the old fixed 0.6), and shuffles brand order per row. Synth output unchanged (`--plain` turns it off). Still missing: players in front of boards get pasted over (needs person masking).
3. ~~**Spike the app-side treatments on the VVD**~~ Done 2026-10-09 (`app/src/cleansheet/TreatmentSpike.tsx`, `matrix4()` in `shared/sidecar/homography.ts`):
   - `transform: [{matrix}]` with `transformOrigin: 'left top'` does a true perspective warp on Vega (test-card corners land on target dots, text foreshortens); replacement art sits on every live board of `tachira_02`.
   - `Image` `blurRadius` works, but only on the image itself: nothing can blur the video under an overlay (separate native surface). **Open problem:** how to obscure boards without a live blur. A flat "frost" colour fill was proposed and rejected (2026-10-09) because it doesn't read as blur. Candidates: a cloud-computed colour mosaic per board drawn with the proven warp, cloud-blurred patch images, pre-rendered blurred variants switched via MSE, always replacing instead of blurring, or a native video filter if Vega has one. Mock up the first two on the VVD and decide before step 4's obscuring work.
   - **Obscuring mock-ups done 2026-10-09; decided: (A) the blurred texture per board.** `pipeline/board_textures.py` straightens each board out of 5 frames of the stream, median-combines them, and writes one PNG per board id: (A) blurred, (B) a 12x3 colour mosaic upscaled with hard edges. The app warps it with `matrix4` onto the quad grown 1.5 px (`growQuad`), one view per board; `SPIKE_MODE` in `app/src/cleansheet/config.ts` switches them. Screenshots: `media/mockups/`. LED rows with changing content would need a texture per segment.
   - Perf (VVD, ~35 warped boards, state update every animation frame): 42-70 updates/s, above the video's 30 fps. With ~140 extra debug dot views it fell to 27-35, so keep the per-frame view count low; next optimizations if needed: update only when the sidecar frame changes, or drive transforms with Reanimated.
   - Original task: Two unknowns: does Vega RN honour a `matrix` transform (for warping replacement art with `cssMatrix3d`'s math), and is there any blur/backdrop-filter on Vega? Fallbacks: per-board pre-warped replacement images, and an opaque "frosted" fill instead of a live blur.
4. ~~**Treatments + category filtering in the app**~~ Done 2026-10-10 (`app/src/cleansheet/SponsorTreatments.tsx`, `prefs.ts`): hidden-category boards get a warped replacement sponsor at confidence >= 0.6, else their blurred texture; viewer prefs live in a small external store (default: gambling + alcohol hidden) for step 5's UI; spike removed; `make clip` now builds textures. Verified on the VVD on `tachira_02` (replace and forced-blur screenshots). Sync re-test with treatments on: 8 of 11 samples on the displayed frame, 3 one frame ahead, 28-30 updates/s. Open polish: replacements look crisper and brighter than the footage (pre-soften and tone them per clip in the pipeline, like `composite.py` does). Original task: Replace (warp a replacement sponsor onto the quad) for boards, the blurred board texture (option A, `pipeline/board_textures.py`) for low confidence; `filterObjects` with the viewer's categories; turn `TREATMENT_SPIKE` and `SYNC_TEST` off. Then **re-run the sync test** (`make synctest`), since the render path changes (CLAUDE.md requires it).
5. **Category toggle UI with D-pad focus** (Claude, then you test with the remote). Settings panel over the player: gambling / alcohol toggles, and a per-category treatment choice (Auto / Replace / Blur, already in `prefs.ts`: `setCategoryTreatment`); follows the Vega focus-management guidance.
6. **Replace the sports sample's images** (Claude). Our own fictional art for hero, thumbnails and profiles; removes the Adidas logos.

Then the Week 2 build below, in this order: detector (needs the composites from 1-2) → model sidecar and precision/recall → AWS (ask before creating anything) → app reads prefs from the API.

Decisions to make on the way:
- **Jersey sponsors:** at broadcast wide-shot size they're illegible, and Vega can't blur video, so there is no treatment for them. Proposal: out of scope.
- **Detector output shape (the user's call):** YOLO boxes can't drive a homography warp. Two options:
  - (a) YOLO segmentation, then fit a 4-corner quad to each mask.
  - (b) Reviewer's suggestion: YOLO pose with 4 keypoints (`kpt_shape: [4, 3]`) predicts the corners directly, no fitting step. Labels come straight from the ground-truth quads; the visibility flag marks off-screen corners.
  Either way, low-confidence boards get the obscuring treatment.
- **Person masking:** players get pasted over in the composite and will be covered by live replacements in the app too (the device can't mask them). Plan: YOLO person segmentation in `composite.py` to paste players back on top; for the app, pick demo moments with few players crossing the boards and state the limitation in the README.

### Week 2: Oct 15 to 20 (build)

- [ ] Generate the training set from composited frames; train a small YOLO. The current export is only 72 frames per clip (every 5th), 288 real frames from one match: export more frames (`--frame-stride 1` or 2), train on synth + tachira_01..04, and hold out a clip cut from a **different VTV match** so precision/recall isn't optimistic.
- [ ] Add tracking between detections and per-board homography estimation.
- [ ] Run inference offline on the Mac; publish HLS + sidecar track to S3/CloudFront.
- [ ] **Sidecar v2, before the AWS step:** a per-board `tracks` table (kind, category, brand, obscuring-texture URL) instead of repeating those fields every frame, coordinates rounded to 4 decimals, `bbox` dropped (computable from the quad). Change `schema.json`, `types.ts` and `pipeline/sidecar.py` together. Today's sidecar is 2.6 MB of JSON per 12 s clip (~400 KB gzipped).
- [ ] Set up the $5 AWS billing alert (from the risks table) before creating any AWS resource.
- [ ] Turn on CloudFront compression for the sidecar JSON.
- [ ] Lambda + DynamoDB sponsor-inventory API (viewer prefs, replacement sponsor per slot), keyed on (video_id, board id) -> replacement brand, replacing the client-side `hashIndex` in `TreatmentSpike.tsx`.
- [ ] Person masking in `composite.py` (YOLO person segmentation, players pasted back on top).
- [x] Implement board replacement (homography warp) and the obscuring treatment for low-confidence boards in the app. (Done early, 2026-10-10: step 4 above.)
- [ ] Match replacement sponsors' softness and light level to the footage (pipeline-side, per clip).
- [ ] Build category toggle UI with proper TV focus navigation.
- [ ] Measure precision/recall against ground truth.

### Final stretch: Oct 21 to 23 (ship)

- [ ] Polish UI and failure handling: low-confidence detections get the obscuring treatment; short gaps are covered by `objectsAt`'s track hold (0.25 s); a board the detector misses entirely can't be treated.
- [ ] Record demo video, under 3 minutes, best material first: side-by-side before/after, toggle switching live, accuracy numbers. **Show the blur on purpose:** ground-truth sidecars are always fully confident, so `auto` only replaces; switch a category to Blur in the settings panel (or `DEFAULT_TREATMENTS` in `app/src/cleansheet/config.ts`), e.g. gambling replaced and alcohol blurred in the same shot. If the detector lands, its low-confidence boards show `auto` falling back to blur.
- [ ] Write README with run instructions, architecture diagram, license records for all footage.
- [ ] Write product feedback for every tool used (Vega SDK, Builder Tools MCP, AWS services).
- [ ] Finalize friction log (up to 10% judging bonus).
- [ ] Decide repo visibility by Oct 21: public with the OSS license, or private with the reviewers invited as collaborators at submission time (invites expire after 7 days).
- [ ] Check the AWS bill and remove anything not needed for judging; submit before 3:00pm ET Oct 23.

### Stretch goals (only if ahead)

- Audio sponsor-read muting via ASR.
- Commercial-break classification and swap.
- Alcohol category.

---

## 6. Submission Checklist

- [ ] Text description: what it does and how it works
- [ ] GitHub repo (public with OSS license, or private shared with reviewers: chris-trag, knmeiss, giolaq, anishamalde, mosesroth, emersonsklar + Devpost)
- [ ] Demo video < 3 min on YouTube/Vimeo, public, English, running on Vega simulator or device
- [ ] Product feedback on every tool/API/SDK, including AWS services used
- [ ] Track: Fire TV; Mini challenge: AWS Builder (with its required fields)
- [ ] Optional: feature requests and friction log

---

## 7. Risks

| Risk | Mitigation |
| --- | --- |
| Overlay drifts out of sync with video | Proven on the VVD in week 1: a 3-4 frame lag, corrected by a fixed 0.117 s offset with snapped lookups (8 of 12 samples exact, rest 1 frame off). MSE segment-swap fallback not needed so far |
| Detector struggles on real motion | Synthetic data with augmentation; obscuring treatment on low confidence |
| Vega SDK friction slows progress | Lean on Builder Tools MCP; log every issue for the friction log bonus |
| Footage licensing questioned | Use only CC0/CC BY, keep license records in the repo |
| AWS costs (no credits) | No GPU instances; offline inference; only always-free or near-free services; billing alert at $5 |
