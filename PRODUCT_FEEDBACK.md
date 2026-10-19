# Product Feedback

For the Devpost submission: one section per question, covering every tool, SDK and AWS service Cleansheet used. Specific incidents, with time lost and workarounds, are in `FRICTION_LOG.md`.

## Which developer tools, APIs and SDKs did you use, and for what?

**Fire TV / Vega**

| Tool | What we used it for |
| --- | --- |
| Vega SDK 0.24 and CLI (`vega`) | Building the app (`build-kepler`), installing and launching it (`vega run-app`), device control (`vega device run-cmd` with `inputd-cli` for scripted remote presses) |
| Vega Virtual Device | The test and demo target (Apple Silicon Mac) |
| React Native for Vega (RN 0.83) | The whole app. Replacement sponsors are `Image` views warped onto each board with a perspective `transform: [{matrix}]` |
| W3C Media API (`HTMLMediaElement`, `KeplerVideoSurfaceView`, Shaka Player) | HLS playback. `currentTime` drives the overlay sync |
| `vega-sports-app` sample | The app shell: profiles, catalogue, details pages, player, focus handling |
| Amazon Devices Builder Tools MCP (in Claude Code) | Project setup (`init-context`, `set_project_context`) and Vega docs lookup: getting-started, media playback, focus management, remote buttons, CLI reference, the screenshot tool, plus searches on perspective transforms, blur support and reaching the host Mac from the Virtual Device |

**AWS** (one CloudFormation stack, `us-east-2`, Free plan)

| Service | What we used it for |
| --- | --- |
| Amazon S3 | Private bucket holding the HLS streams, sidecar tracks (per-frame board positions), board textures, sponsor art and catalogue images |
| Amazon CloudFront | The CDN in front of S3 for everything the app loads: origin access control (the bucket stays private), Brotli/gzip compression, CORS |
| AWS Lambda (function URL) | The sponsor-inventory API: each viewer profile's hidden categories and treatments (`GET/PUT /viewers/<id>/prefs`), and the replacement sponsor for every board slot of a video (`GET /videos/<id>/inventory`). Python 3.12 on arm64, reserved concurrency 5 |
| Amazon DynamoDB | On-demand table behind the API: viewer prefs and per-slot sponsors |
| AWS CloudFormation | The whole stack in one template (`cloud/template.yaml`), deployed with `cloud/deploy.sh` |
| AWS Budgets | A $5/month alert, set before any other resource |
| AWS CLI (`aws login`) | Deploys, uploads, cache invalidations, seeding the table |
| Amazon Bedrock | Evaluated for generating demo footage (not used, see below) |

## What worked well?

**Vega**

- **Perspective transforms work on Vega.** A full 4x4 `matrix` transform with `transformOrigin: 'left top'` gives a true projective warp: replacement art sits on boards seen at an angle and follows them through camera pans. This is the feature the whole app depends on; a short spike on the Virtual Device confirmed it on day two.
- **The W3C Media API made frame-accurate overlays possible.** Video plays on a native surface and React Native views stack on top of it. `currentTime` lags the picture by a constant 3 to 4 frames on the Virtual Device. With a fixed offset, the overlay lands on the displayed frame in 8 of 12 measured samples and is never more than one frame off.
- **Overlay performance was enough.** About 35 warped boards updating with every video frame held 29 to 30 updates per second, matching the 30 fps video.
- **The `vega-sports-app` sample was a big head start.** Profiles, catalogue, details pages, a Shaka-based player and D-pad focus came ready-made, so our time went into the overlay and the cloud, not the TV shell.
- **Scripted testing.** `vega device run-cmd "inputd-cli button_press KEY_ENTER"` let us drive the app from scripts, and `vega run-app` builds, installs and launches in one step.
- **The Virtual Device runs well on Apple Silicon** once booted, and is accepted for judging, so no hardware was needed.
- **The Builder Tools MCP answered docs questions inside the editor.** The focus-management guide shaped our settings panel, and the remote-buttons and CLI references were quicker to reach than browsing the docs site.

**AWS**

- **CloudFront compression paid off immediately.** A 12 s clip's sidecar track goes over the wire as 231 KB with Brotli, from 1.07 MB of JSON, with one template setting (`Compress: true`) and a managed cache policy.
- **Origin access control** kept the bucket fully private with a short bucket policy, and the managed CORS policies covered the app's requests without custom headers.
- **Lambda function URLs** were the right size for a small API: no API Gateway to configure, CORS set on the URL, and reserved concurrency as a simple cost cap on a public endpoint.
- **DynamoDB on-demand** with a single table (`pk`/`sk`) covered both item types (viewer prefs, slot sponsors) with no capacity planning, at zero cost at demo scale.
- **One CloudFormation template** made the stack reviewable and repeatable, with one-line teardown.
- **AWS Budgets** let us set a $5 alert on spend before credits on day one, so the Free-plan credits couldn't hide real costs.

## What needs work?

**Vega SDK, CLI and Virtual Device**

- **No screenshot or screen recording on the Virtual Device.** The screenshot tool (`gwsi-tool-screenshooter`) only supports physical devices. Every visual check needed a macOS window capture workaround (`scripts/vvd_screenshot.sh`), which fails if the window is minimized or on another Space.
- **No presented-frame timestamp.** There's no `requestVideoFrameCallback` or equivalent, and `currentTime` advances in whole-frame 33 ms steps, which isn't documented. Measuring sync took a burned-in frame-number stream and screenshots.
- **No way to blur the video under an overlay.** `blurRadius` only blurs an `Image`. Obscuring a board needed per-board blurred textures pre-rendered in the cloud. A backdrop blur or video filter would remove that whole pipeline step.
- **Virtual Device reliability.** The first boot exceeds the default 60 s timeout. `vega device list` and `run-app` sometimes hang with no output or timeout until the device is stopped and stuck `vda` processes are killed. `run-app` right after "Virtual device ready" can fail with "Device not found". Once, the display froze while the app kept running.
- **The build rewrites the checked-in `manifest.toml`** on every build: it adds about 30 auto-detected module entries plus a growing run of blank lines, so the file always shows as modified.
- **CLI paper cuts.** `vega project generate -o <dir>` writes into `<dir>` itself rather than `<dir>/<name>`. `loggingctl` only returned the last ~135 log lines of a 12 s run.

**React Native for Vega docs**

- The Transforms page lists `matrix` but doesn't say whether perspective terms are honoured, and the Image page doesn't say that nothing can blur content behind a view. Both took an on-device spike (about 45 minutes) to answer. One sentence each would have settled it.
- `requestAnimationFrame` fired 900 to 3,000 times a second on the Virtual Device instead of once per display frame. That's worth documenting, because an overlay that sets state on every callback re-renders far more often than the screen can show.

**`vega-sports-app` sample**

- `npm install` builds Shaka Player and needs Java 21+, but doesn't check the version first. It failed with the default JDK.
- Its `lefthook` dev dependency installs git hooks into the enclosing repository when the sample is vendored into a subfolder.
- Its `manifest.toml` requests microphone access, which a video sample doesn't need. The Mac's microphone indicator came on while the Virtual Device ran.
- The player's seek bar uses `hasTVPreferredFocus` and the control bar re-mounts on key presses, which pulled focus out of our own panel. The player also exits to the details page when a video ends.
- Several catalogue images come from a CDN with real brand logos, which a hackathon demo can't show.

**Builder Tools MCP**

- `init-context` appended about 210 lines of always-on rules to an existing `CLAUDE.md` and installed a skill globally, without asking. Writing to its own file and offering an import line would be gentler.
- The rules it adds are heavy for every conversation (a mandatory welcome message, a six-step session setup before any request). They're useful for platform detection, but they cost context in sessions that never touch Vega.

**AWS**

- **`aws login` sessions expire between work sessions**, and every CLI call then fails until someone signs in through a browser. Long unattended jobs (train, then publish) stall at the AWS step.
- **No AWS video-generation model was available.** Nova Reel reached end of life on 2026-09-30 and was never offered in us-east-2, the Free-plan project's only Region. The alternative (Luma Ray2 via Marketplace) costs about $1.50 per second of 720p, so we kept compositing onto public-domain footage.

## How was your onboarding experience (zero to hello world)?

**Vega:** good overall. Install, hello world on the Virtual Device, the sports sample playing our own HLS stream, and the first overlay sync measurement all happened on day one (Oct 8). Roughly 25 minutes went to setup problems:

- the installer skipped the Vega Studio extension in non-interactive mode
- the first boot timed out at the default 60 s
- `vega device list` hung after a "ready" device, fixed by restarting it
- `project generate` wrote into the wrong directory

Each had a quick workaround, and the docs found through the MCP covered the next steps (media playback, focus management, reaching the Mac from the device at `10.0.2.2`). The sports sample's Java 21 requirement for its Shaka build was the other early stumble.

**AWS:** smooth. The Free plan's single Region and the `aws login` profile were the only things to learn. From an empty project to a deployed CloudFront + Lambda + DynamoDB stack was a single CloudFormation deploy. The billing alert was the first thing created.

## Would you build with these devices and services again?

_Draft for the team to confirm:_

**Yes.** Vega handled the hard part, a perspective-warped overlay that stays frame-synced with video, using standard React Native and W3C Media APIs, and the sports sample saved days. A screenshot tool and a presented-frame timestamp on the Virtual Device are the two things we'd most want for the next project.

**Yes for AWS:** CloudFront, Lambda function URLs and DynamoDB on-demand were exactly the right size for a per-viewer API and a compressed metadata CDN, at no cost at demo scale.

## Feature requests

| Request | Why it matters to Cleansheet | Priority |
| --- | --- | --- |
| Screenshot and screen recording on the Vega Virtual Device | Every visual check of the overlay needed a macOS capture workaround | Important |
| A presented-frame timestamp (`requestVideoFrameCallback` or similar) | Frame-accurate overlays need to know which frame is on screen, not just `currentTime` | Important |
| Backdrop blur, or a filter on the video surface | Obscuring part of the video needed a pre-rendered texture per board | Important |
| Builds that don't rewrite the checked-in `manifest.toml` | It shows as modified after every build | Nice-to-have |
| Docs: state that `matrix` supports perspective, and that `blurRadius` can't blur content behind a view | Each took an on-device spike to find out | Nice-to-have |
| A longer `aws login` session, or a refresh that works unattended | Long pipeline runs stall at the upload step | Nice-to-have |
