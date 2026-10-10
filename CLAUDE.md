# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Cleansheet

Fire TV (Vega OS) sports app that detects sponsor content in its own video stream with computer vision and replaces or obscures it per viewer, based on chosen categories (gambling, alcohol, custom). Built for the Amazon Developer Hackathon "Build, Ship, Shape": Fire TV track plus the AWS Builder mini challenge.

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
- Treatments: homography-warped replacement for perimeter boards and banners (proven on the VVD with `matrix4`). Vega can't blur the video from an overlay (`blurRadius` blurs only an image), so low-confidence detections get a cloud-made blurred texture per board (`pipeline/board_textures.py`) warped like a replacement; a flat colour fill and the mosaic were rejected. A board the detector misses entirely can't be treated; `objectsAt` only holds a track over short gaps. Jersey sponsors and true inpainting are out of scope.
- Detection: optionally bootstrap with an open-vocabulary detector (Grounding DINO / OWL-ViT), then fine-tune a small YOLO on synthetic composited data.

## Repo layout and commands

- `shared/sidecar/`: the sidecar contract. `schema.json` is the source of truth; `types.ts` and `pipeline/sidecar.py` mirror it, so change all three together. `sync.ts` (`objectsAt`, `filterObjects`) and `homography.ts` (`cssMatrix3d`) are meant to be reused by the Vega app.
- `pipeline/`: Python (run with `.venv/bin/python`; scripts import sibling modules directly). Order: brands → synth_clip, or for real footage find_shots → cut_clip → annotate → composite → package_hls.sh.
- `cloud/mock_server.py`: serves `media/` and `assets/` on :8787 with CORS (`--host 0.0.0.0` for the Virtual Device).
- `harness/`: Vite page that plays HLS and draws overlays; the testbed for sync before Vega. `?clip=<name>` picks the clip; it compares the `currentTime` clock (what Vega exposes) against `requestVideoFrameCallback` and has an offset slider for calibrating skew.
- `app/`: Vega app (RN 0.83), forked from `vega-sports-app`; its own npm project. Build/run steps are in `app/README.md`. Needs `JAVA_HOME=/opt/homebrew/opt/openjdk@21` for `npm install` (Shaka build). From the Virtual Device the Mac is `10.0.2.2`, so streams point at `http://10.0.2.2:8787/...`. Vega's screenshot tool doesn't work on the VVD; use `scripts/vvd_screenshot.sh out.png` (window must be on screen). Overlay code lives in `app/src/cleansheet/`, which imports `shared/sidecar` as `@Sidecar`. Measure sync with `make synctest` plus `SYNC_TEST` in `app/src/cleansheet/config.ts` (procedure in `app/README.md`); on the VVD `currentTime` trails the picture by 3-4 frames, corrected by `SYNC_OFFSET_S` (0.117 s). A per-frame ground-truth sidecar is looked up snapped (`interpolate: false`, chosen by `samplesVideoFrames`); interpolation is only for sparse model tracks. On Vega `currentTime` advances in whole-frame 33 ms steps, so an interpolated per-frame track lands at a fixed phase (~95% toward the next frame with the current offset): measured on the VVD, 2.3 px mean / 11.4 px max off the displayed frame over 2.2 s of `tachira_02`, ~20 px in its fastest pan. `SYNC_LOG` in `app/src/cleansheet/config.ts` logs each render's player time for this kind of measurement.
- `media/` and footage video files are generated or downloaded and are git-ignored.

### Pipeline data flow

- Real footage: `find_shots.py` lists uncut wide-camera stretches in a full broadcast; `cut_clip.py` cuts one to 720p30, drops audio, and pixelates fixed graphics (scorebug, channel logos) via `--mask`. The four current clips come from a public-domain VTV broadcast; `footage/tachira.sh` re-downloads (to `media/sources/`) and re-cuts them. Uncomposited real clips still show real sponsors on the boards.
- `footage/<clip>.boards.json` (format documented in `pipeline/boards.py`) holds per-board corner quads in pixels (TL, TR, BR, BL): sparse hand-clicked `keyframes` plus optional dense `frames`. `synth_clip.py` writes dense `frames` as exact ground truth; `annotate.py` (interactive OpenCV window, so a person has to run it) keyframes real clips and densifies them with optical flow. A board with `split: N` is a whole planar row of boards: `boards.expand` splits it into N boards (`<id>-01`...) and `extend` continues it past the clicked quad; everything downstream sees plain boards. A single keyframe is tracked across the whole clip. Broadcast clips set top-level `"tracking": "camera"`: one whole-frame homography per frame (pan/tilt/zoom from a fixed spot) moves every board, which is far more stable than per-board tracking against animated LED boards; it still drifts several px over 12 s, so long rows need correction keyframes every ~60-120 frames.
- `composite.py` pastes fictional brands onto those quads and writes `media/<clip>/`: `composited.mp4`, ground-truth `sidecar.json` (normalized quads), a YOLO dataset (`dataset/images`, `dataset/labels`, `classes.txt`), and `manifest.json`. The compositor pastes over anything in front of a board (no occlusion masking yet).
- `package_hls.sh` turns `composited.mp4` into `media/<clip>/hls/index.m3u8`.
- `ui_art.py` regenerates the app's catalogue images in `assets/ui/` (committed) from exactly the URLs the app's static JSON references; re-run it after adding image URLs to `app/src/api/*/staticData/`. Never point the app back at the sample's CDN (real brands).
- `board_textures.py media/<clip>` writes one obscuring texture per sidecar board id (`textures/blur/`, `textures/mosaic/`, `textures/index.json`), straightened from the composited stream and median-combined over 5 frames. The app warps them with `matrix4` onto `growQuad`-grown quads (`app/src/cleansheet/SponsorTreatments.tsx`: hidden boards below `REPLACE_MIN_CONFIDENCE` get the blurred texture, the rest a replacement sponsor). Never draw a mosaic as individual Views: one image per board.
- Brand categories (`pipeline/brands.py`): `gambling`, `alcohol` (hideable), `neutral` (stays on screen; detector negatives), `replacement` (swapped in).
- Every clip in `footage/` must have a license entry in `footage/LICENSES.md`.

### Commands

```sh
make setup                 # venv + npm install (needs Python 3.10+, Node 20+, ffmpeg)
make synth                 # brands -> synthetic clip -> composite -> validate sidecar -> HLS
make clip CLIP=<name>      # same for footage/<name>.mp4 (needs footage/<name>.boards.json)
make test                  # vitest + tsc --noEmit + tracker accuracy vs synthetic ground truth
make serve                 # mock CDN on :8787;  make harness  # Vite harness on :5173
npx vitest run shared/sidecar/sync.test.ts     # single test file (add -t "<name>" for one test)
.venv/bin/python pipeline/sidecar.py <path>    # validate a sidecar JSON against the schema
.venv/bin/python pipeline/annotate.py footage/<clip>.mp4   # annotate boards on a real clip
```

Vitest only picks up `shared/**/*.test.ts`. There are no Python unit tests; `check_tracking.py` is the Python-side check.

HLS is packaged with B-frames off and timestamps starting at 0 so `currentTime` lines up with sidecar `t`; keep it that way.

## Stack

- **Vega SDK:** 0.24 (CLI 1.4), installed at `~/vega`. Boot the device with `vega virtual-device start -t 300` (the default 60 s timeout is too short for the first boot). If `vega device list` or `run-app` hangs, stop the device, `pkill -f "vda -s emulator"`, and start it again.

- **App:** Vega OS + React Native. Shell forked from `vega-sports-app`; player code borrowed from `vega-video-sample` (MIT-0).
- **Cloud:** no hackathon credits (only the Free plan credits below). S3 + CloudFront (HLS + sidecar JSON) and Lambda + DynamoDB (per-viewer sponsor-inventory API). Inference runs offline on the Mac (PyTorch MPS); no GPU instances.
- **Test target:** Vega Virtual Device (accepted for submission and judging).
- **Dev tooling:** Amazon Devices Builder Tools MCP:
  `npx -y @amazon-devices/amazon-devices-buildertools-mcp@latest init-context`

## Hard rules

- **No real trademarks or brands anywhere in demo footage, assets, or screenshots.** Use only fictional brands (e.g. "BetNova", "SpinStake") and fictional replacement sponsors.
- **Footage must be CC0 or CC BY** (Pixabay CC0, Wikimedia Commons). Record the license for every clip in the repo. Never use Getty/Pond5 editorial clips, Pexels bulk downloads for training, or SoccerNet video in anything shipped or demoed.
- Cleansheet only filters streams in its own player; it cannot touch other apps (sandboxing, DRM). Don't design features that assume otherwise.
- **AWS project:** profile `cleansheet`, Region `us-east-2` (all regional resources go there), Free plan with $100 credits (expires 2027-04-09). Sign in with `aws login --profile cleansheet` when credentials expire.
- **AWS costs:** there are no hackathon credits. Use only always-free or near-free services (CloudFront, Lambda, DynamoDB, small S3). Never launch GPU/EC2/SageMaker resources. Ask before creating or deleting cloud resources.
- TV UI must support proper D-pad focus navigation.

## Working conventions

- Pitch and user-facing copy frame the product as **per-viewer sponsor inventory**, not "removing sponsors".
- Keep a running friction log in `FRICTION_LOG.md` (table: date, tool, task, what went wrong, time lost, fix) of every Vega SDK / Builder Tools MCP / AWS issue hit (it counts for up to a 10% judging bonus). Add entries as problems come up.
- Overlay sync with `currentTime` was the riskiest piece; it's proven on the VVD (on the displayed frame in 8 of 12 samples, never more than 1 off, with a 0.117 s offset and snapped lookups). Re-check with the sync test after changing the player, packaging, or overlay render path.
- When the compositing script runs, it should output per-frame ground-truth labels alongside the video; use them for training data and precision/recall numbers.

## Amazon Devices Builder Tools MCP

The `amazon-devices-buildertools-mcp` server (Vega docs search, device tooling) is configured for Claude Code. Its official usage guide, generated by `init-context`, is imported below. Re-running `init-context` appends to this file again, so move any new content back into `.claude/amazon-devices-context.md`.

@.claude/amazon-devices-context.md

<!-- BEGIN AWS Agent Toolkit rules -->
# AWS Guidance for the new AWS experience

This user has signed up for the new AWS experience. This experience lets you sign into AWS using a social provider and requires the following additional context.

Where this guidance conflicts with the project's own instructions, the project's instructions take precedence.

## Context

### Terminology:

- Say "project" instead of "account" — a project contains an AWS account and settings for sharing with other collaborators
- Say "team member" instead of "IAM user" — users are invited by email, not created or federated in IAM
- Say "AWS Settings" when referring to management tasks at [settings.aws.com](https://settings.aws.com/) (project management, billing, team members, spend limits). Users view their actual AWS resources in the AWS Management Console.
- Say "selected Region" when referring to the user's Region — not "home Region"
- The user has a managed IAM experience. This includes a managed service control policies (SCP) and resource control policies (RCP) that govern the use of AWS. They will still need to use IAM to create policies to let services work with each other. If there are questions about the SCPs or RCPs, go to the documentation at https://docs.aws.amazon.com/accounts/latest/reference/scps-and-rcps-for-projects.html

### Constraints:

- All projects share a single AWS Region determined by the user's contact address. Resources cannot be created in other Regions
- When developing:
  - MUST create all Regional resources in the project's assigned Region
  - You CAN create AWS WAF and Cloudwatch Logs resources in us-east-1 when there are global resources (like a global WAF instance) that require a connection to dependencies in us-east-1. You should not use these for any other reason, because resources in the selected Region will provide lower cost (due to no cross-Region traffic), increased availability (due to no cross-Region traffic), and easier manageability (due to not needing to look in another Region). When you need to do an inventory of resources, you need to look in both the selected Region and us-east-1 for Cloudwatch Logs or WAF resources.
  - MUST NOT attempt to create Lambda, API Gateway, or other Regional resources in any other Region
  - MUST direct users to confirm their Region in AWS Settings > View all projects > Overview > Additional Info > Region. If the user cannot confirm their Region, check in ~/.aws/config
  - MUST NOT use Lambda@Edge — excluded from both Lambda and CloudFront
  - MUST NOT use CloudFormation StackSets — no multi-account or multi-Region deployments
  - MUST NOT attempt cross-Region actions — no cross-Region replication for DynamoDB/S3/RDS, no multi-Region KMS keys
  - MUST NOT use Route 53 cross-Region routing — geolocation, latency-based, and failover routing policies are not available
  - CloudFront is a global service and its actions ARE allowed in `us-east-1`. A user can create a CloudFront distribution pointing to their project-region Lambda function URL or API Gateway. However, Lambda and API Gateway themselves MUST NOT be created in `us-east-1` — they must be in the project Region.
  - Reduced availability in `eu-north-1` specifically: Amazon Rekognition, Amazon Textract, Amazon Personalize, AWS App Runner are not available in that Region.
- IAM permissions for human access are managed by AWS. Don't assign roles to team members unless absolutely necessary
- The user may have a spend limit if they are on the paid plan. The limit that pauses their project if it's exceeded. If resources suddenly become inaccessible, ask if they have a spend limit configured. Only project owners can modify a spend limit.
- When developing:
  - MUST ask about spend limit status if the user reports sudden "Access Denied" errors on operations that previously worked
  - MUST direct users to check spend status in AWS Settings > Billing
  - MUST check if a user has upgraded their account to the paid plan
  - MUST ask the user if they want to clean up the successfully created resources or keep them to reduce cost
- The user sets up billing, creates spend limits, and retrieves and pays invoices in AWS Settings. The user creates budgets and optimizes their costs in the AWS Billing and Cost Management console
- Not all AWS services are available. If a service isn't working, do the following:
  1. Run the command `aws freetier get-account-plan-state`
  2. If accountPlanType": "FREE", check the [Free Tier supported services list](https://docs.aws.amazon.com/accounts/latest/reference/supported-services-sign-up-new.html#supported-services-free-tier) next,
  3. If accountPlanType": "PAID", check the [Paid Tier supported services list](https://docs.aws.amazon.com/accounts/latest/reference/supported-services-sign-up-new.html#supported-services-paid-plan).
  4. If neither list shows the service, check the [Not supported for this experience list](https://docs.aws.amazon.com/accounts/latest/reference/supported-services-sign-up-new.html#unsupported-services). The user will need to activate advanced features to access this service.
- Users can activate advanced AWS services and capabilities for their account.
- Before starting a task, check whether a relevant AWS skill is available. Load the skill with retrieve_skill and prefer its guidance over general knowledge.

### Help level

- help_level (required): LOW, MEDIUM, or HIGH. While a user is building, you MUST ask the user: "How much guidance would you like from me? Low (I only flag security risks), medium (I ask a couple of clarifying questions if something seems off), or high (I explain what I'm doing, suggest alternatives, and flag best practices)."

You CAN update this rule file to save a user's help_level.

Constraints for each level:

**LOW:**

- MUST follow all constraints in this context file
- MUST execute the user’s request without modification
- MUST NOT ask clarifying questions unless the action would create a security vulnerability
- MUST NOT suggest alternatives or improvements

**MEDIUM:**

- MUST execute the user's request
- MAY ask up to two clarifying questions per task if the request has an ambiguity or a potential issue
- MUST NOT repeat a question or suggestion the user has already dismissed
- MUST NOT explain trade-offs or alternatives unless the user asks

**HIGH:**

- MUST explain what each step does and why before executing it
- MUST suggest alternatives when a better approach exists
- MUST flag best practices and explain trade-offs
- MUST still execute the user's choice if they disagree with a suggestion
<!-- END AWS Agent Toolkit rules -->
