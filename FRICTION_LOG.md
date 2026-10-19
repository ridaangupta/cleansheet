# Friction Log

Every snag hit with the Vega SDK, the Vega Virtual Device, React Native for Vega, the `vega-sports-app` sample, the Amazon Devices Builder Tools MCP and AWS while building Cleansheet, logged as it happened (Oct 8 to 19, 2026; Vega SDK 0.24, macOS on Apple Silicon). The highlights are also in `PRODUCT_FEEDBACK.md`.

**Severity:** **High** = blocked the task until a workaround was found, or lost work. **Medium** = cost real time or needed a non-obvious workaround. **Low** = a paper cut with a quick fix.

## Summary

| # | Date | Tool | Issue | Severity | Time lost |
| --- | --- | --- | --- | --- | --- |
| 1 | Oct 8 | Vega Virtual Device | `vega device list` / `run-app` hang after a "ready" boot | High | 10 min |
| 2 | Oct 8 | Vega Virtual Device | Display froze while the app kept running | High | 10 min |
| 3 | Oct 8 | Vega CLI | Screenshot tool doesn't work on the Virtual Device | High | 5 min, then a workaround on every visual check |
| 4 | Oct 8 | W3C Media on Vega | No presented-frame timestamp to measure overlay sync | High | 20 min |
| 5 | Oct 9 | `vega-sports-app` | Sample requests microphone access it doesn't use | Medium | 15 min, device stopped mid-test |
| 6 | Oct 9 | React Native for Vega docs | Perspective `matrix` and blur support undocumented | Medium | 45 min |
| 7 | Oct 9 | React Native for Vega | `requestAnimationFrame` fires 900-3,000 times/s | Medium | 15 min |
| 8 | Oct 9 | W3C Media on Vega | `currentTime` moves in whole-frame steps; `loggingctl` truncates | Medium | 30 min |
| 9 | Oct 10 | `vega-sports-app` | Player's seek bar steals focus from an overlay panel | Medium | 30 min |
| 10 | Oct 8 | Vega Virtual Device | First boot exceeds the default 60 s timeout | Medium | 5 min |
| 11 | Oct 8 | Builder Tools MCP | `init-context` appends ~210 lines to an existing CLAUDE.md | Medium | 5 min |
| 12 | Oct 8 | `vega-sports-app` | `npm install` needs Java 21+ but doesn't check | Medium | 5 min |
| 13 | Oct 8 | `vega-sports-app` | `lefthook` installs git hooks into the parent repo | Medium | 5 min |
| 14 | Oct 14 | Amazon Bedrock | No video-generation model available | Medium | 20 min |
| 15 | Oct 14 | AWS CLI | `aws login` session expiry stalls unattended steps | Medium | 5 min per session |
| 16 | Oct 8 | Vega SDK installer | Non-interactive install skips the Vega Studio extension | Low | 2 min |
| 17 | Oct 8 | Vega SDK installer | Shell profiles edited without listing the lines | Low | 0 |
| 18 | Oct 8 | Vega CLI | `project generate -o` writes into the given directory | Low | 2 min |
| 19 | Oct 8 | Vega Virtual Device | `run-app` right after "ready" says no device | Low | 2 min |
| 20 | Oct 8 | Vega build | Every build rewrites the checked-in `manifest.toml` | Low | 5 min |
| 21 | Oct 9 | Vega Virtual Device / macOS | Window capture fails when the VVD window is off screen | Low | 10 min |
| 22 | Oct 10 | `vega-sports-app` | Player exits to the details page when a video ends | Low | 5 min |

Total time lost: about 4 hours.

## Entries

### 1. `vega device list` and `run-app` hang after a "ready" boot (High)

- **Task:** run the hello-world app on a freshly booted Virtual Device (Oct 8).
- **Steps:** `vega virtual-device start -t 300` → "Virtual device ready" → `vega device list` → `vega run-app <vpkg>`.
- **Expected:** the device is listed and the app installs.
- **Actual:** `device list` and `run-app` hung with no output and no timeout. `vda shell echo` also hung: a device-info query from boot was stuck.
- **Workaround:** `vega virtual-device stop`, kill the stuck `vda -s emulator` processes, start again. It worked on the second boot.
- **Suggestion:** give the CLI's device queries a timeout and an error that says the `vda` session is stuck, or have `virtual-device start` check the shell is responsive before reporting "ready".

### 2. Virtual Device display froze while the app kept running (High)

- **Task:** re-run the app while measuring overlay sync (Oct 8).
- **Steps:** run-app, play a stream, press keys on the remote.
- **Expected:** the window shows playback.
- **Actual:** the window stayed on one frame, even after Home. The app was still running: the HLS server logged segment requests and key presses were handled.
- **Workaround:** `vega virtual-device stop`, `pkill -f "vda -s emulator"`, start again.
- **Suggestion:** detect a stalled display surface (or expose a "restart display" command), and add the recovery steps to the Virtual Device troubleshooting docs.

### 3. Screenshot tool doesn't work on the Virtual Device (High)

- **Task:** verify playback and the overlay on screen from a script (Oct 8, and every visual check after).
- **Steps:** looked up the screenshot tool (`gwsi-tool-screenshooter`, via `vega exec vda`) in the CLI docs through the Builder Tools MCP.
- **Expected:** a screenshot of the device screen.
- **Actual:** the tool only supports physical devices. There's no scripted way to capture the Virtual Device.
- **Workaround:** `scripts/vvd_screenshot.sh` finds the Virtual Device window and captures it with macOS `screencapture -l <window id>`. Video checks used `screencapture -v` on the window's rectangle.
- **Suggestion:** support the screenshot tool (and a short screen recording) on the Virtual Device, or have `vega device` capture its window. This was the most-used workaround in the project.

### 4. No presented-frame timestamp to measure overlay sync (High)

- **Task:** measure how far the overlay sits from the video frame on screen (Oct 8). Sync was the project's main technical risk.
- **Steps:** looked for `requestVideoFrameCallback` or a presented-frame time in the player API.
- **Expected:** a way to know which frame is displayed, as in browsers.
- **Actual:** neither exists, so the sync error can't be measured from code.
- **Workaround:** burned frame numbers into a test stream, drew the overlay's frame number in a HUD, captured the window and read the difference off the screenshot. Result: `currentTime` trails the picture by 3-4 frames; a 0.117 s offset fixes it.
- **Suggestion:** add `requestVideoFrameCallback` (or a presented-frame timestamp on the media element) to Vega's W3C Media API, and document the typical `currentTime` latency.

### 5. Sample requests microphone access it doesn't use (Medium)

- **Task:** run the forked `vega-sports-app` on the Virtual Device (Oct 9).
- **Steps:** build and run the sample unchanged.
- **Expected:** a video sample needs no audio-capture privileges.
- **Actual:** its `manifest.toml` requests `com.amazon.audio.privilege.microphone.access`, and the Mac's microphone-in-use indicator came on while the Virtual Device ran. Nothing explains why. The device was stopped mid-test and the build lost.
- **Workaround:** removed the privilege; verified with `vega exec vpt dump <vpkg> manifest.toml`.
- **Suggestion:** drop the privilege from the sample, or comment why it's there.

### 6. Perspective `matrix` and blur support undocumented (Medium)

- **Task:** decide how to warp replacement art onto angled boards and how to blur boards over video (Oct 9).
- **Steps:** read the React Native for Vega Transforms and Image pages; searched the docs through the Builder Tools MCP.
- **Expected:** the docs say whether `matrix` honours perspective terms and whether anything can blur content behind a view.
- **Actual:** the Transforms page lists `matrix` without saying; the Image page's `blurRadius` doesn't say it only blurs the image. Both needed an on-device spike.
- **Workaround:** spike on the Virtual Device: perspective `matrix` works with `transformOrigin: 'left top'`; `blurRadius` blurs only the image, so boards are obscured with blurred textures made in the cloud.
- **Suggestion:** one sentence on each page. Longer term, a backdrop blur or a filter on the video surface.

### 7. `requestAnimationFrame` fires 900-3,000 times a second (Medium)

- **Task:** drive the overlay from an animation loop (Oct 9).
- **Steps:** set React state on every `requestAnimationFrame` callback and counted renders.
- **Expected:** about one callback per display frame (60/s).
- **Actual:** 900 to 3,000 callbacks a second, so the overlay re-rendered far more often than the screen can show.
- **Workaround:** update state only when the sidecar frame changes; the overlay now renders 29-30 times a second.
- **Suggestion:** throttle `requestAnimationFrame` to the display rate, or document the behaviour.

### 8. `currentTime` moves in whole-frame steps; `loggingctl` truncates (Medium)

- **Task:** measure where overlay renders land within a video frame (Oct 9).
- **Steps:** logged `currentTime` on every render and read the log with `loggingctl log -v <package>`.
- **Expected:** a continuous clock, and the whole log of a 12 s run.
- **Actual:** `currentTime` advances in 33 ms steps (one frame at 30 fps), which isn't documented and changes how sync must be designed. `loggingctl` returned only the last ~135 lines.
- **Workaround:** look up per-frame tracks snapped to the frame instead of interpolating; read the log right after a short run.
- **Suggestion:** document `currentTime`'s granularity; let `loggingctl` return the full buffer or a time range.

### 9. Sample's seek bar steals focus from an overlay panel (Medium)

- **Task:** add a settings panel over the player (Oct 10).
- **Steps:** opened a panel over the sample's player and navigated with the D-pad.
- **Expected:** focus stays in the panel.
- **Actual:** the seek bar uses `hasTVPreferredFocus` and the control bar re-mounts on every key press after auto-hiding, so focus jumped to the seek bar a few seconds after the panel opened. `hasTVPreferredFocus` only applies on mount, so it can't return focus to a button when the panel closes.
- **Workaround:** hide the control bar and ignore its key handler while the panel is open; restore focus on close with `FocusManager.focus(ref)`.
- **Suggestion:** avoid `hasTVPreferredFocus` on re-mounting controls in the sample; show focus restoration on close in the focus-management guide.

### 10. First boot exceeds the default 60 s timeout (Medium)

- **Task:** boot the Virtual Device for the first time (Oct 8).
- **Steps:** `vega virtual-device start`.
- **Expected:** the device boots.
- **Actual:** "Deadline reached (60s) but virtual device unresponsive"; the log shows "failed to access shell". The first boot just takes longer.
- **Workaround:** `vega virtual-device start -t 300`.
- **Suggestion:** a longer default timeout on first boot, or an error that suggests `-t`.

### 11. `init-context` appends ~210 lines to an existing CLAUDE.md (Medium)

- **Task:** set up the Builder Tools MCP for Claude Code in a repo that already had a `CLAUDE.md` (Oct 8).
- **Steps:** `npx -y @amazon-devices/amazon-devices-buildertools-mcp@latest init-context -a claude-code-cli -f`.
- **Expected:** a separate context file, or a prompt before editing the project's instructions.
- **Actual:** about 210 lines of always-on rules were appended to `CLAUDE.md`, and a skill was installed globally in `~/.claude/skills`. Re-running appends again.
- **Workaround:** moved the content into `.claude/amazon-devices-context.md` and imported it from `CLAUDE.md`.
- **Suggestion:** write to its own file and print the import line; ask before global installs; make re-runs idempotent.

### 12. `npm install` needs Java 21+ but doesn't check (Medium)

- **Task:** install the forked `vega-sports-app` (Oct 8).
- **Steps:** `npm install`.
- **Expected:** install succeeds, or fails early with the requirement.
- **Actual:** the postinstall Shaka Player build needs Java 21+; the default JDK here was Corretto 11 and the build failed.
- **Workaround:** `JAVA_HOME=/opt/homebrew/opt/openjdk@21` for install and build.
- **Suggestion:** check the Java version in the postinstall script and say what's needed.

### 13. `lefthook` installs git hooks into the parent repo (Medium)

- **Task:** vendor the sample into a subfolder of an existing repo (Oct 8).
- **Steps:** copied the sample into `app/`, ran `npm install`.
- **Expected:** the sample's tooling stays inside its folder.
- **Actual:** its `lefthook` dev dependency installs pre-commit and pre-push hooks into the enclosing git repo, which would run the sample's lint on every commit of the parent project.
- **Workaround:** removed `lefthook.yml` and the dependency before installing.
- **Suggestion:** make the hooks opt-in, or skip install when the sample isn't the git root.

### 14. No video-generation model available on AWS (Medium)

- **Task:** generate demo clips with an AWS video model (Oct 14).
- **Steps:** checked Bedrock model availability in us-east-2, the Free-plan project's only Region.
- **Expected:** an Amazon video model usable from the project's Region.
- **Actual:** Nova Reel reached end of life on 2026-09-30 and was never offered in us-east-2; Nova 2 doesn't generate video. The third-party option (Luma Ray2) costs about $1.50 per second of 720p through Marketplace.
- **Workaround:** dropped the idea; kept compositing fictional boards onto public-domain footage.
- **Suggestion:** a successor video model, or show Region availability and end-of-life dates on the model's Bedrock page.

### 15. `aws login` session expiry stalls unattended steps (Medium)

- **Task:** every AWS step: deploys, uploads, seeding the table (Oct 14 on).
- **Steps:** run `cloud/publish_media.sh` after a multi-hour training run.
- **Expected:** credentials last through the session, or refresh without a browser.
- **Actual:** the `cleansheet` profile's session expires between work sessions; every call fails with "Your session has expired" until someone signs in through a browser.
- **Workaround:** `aws login --profile cleansheet` at the start of each AWS session.
- **Suggestion:** a longer session option for Free-plan projects, or an unattended refresh for CLI jobs.

### 16. Non-interactive install skips the Vega Studio extension (Low)

- **Task:** install the Vega SDK (Oct 8).
- **Steps:** ran `get_vvm.sh` with `NONINTERACTIVE=true`, VS Code installed.
- **Expected:** the Vega Studio extension installs.
- **Actual:** it was skipped; the installer only printed a Marketplace link.
- **Workaround:** `code --install-extension amazon-devices.kepler-studio`.
- **Suggestion:** install it in non-interactive mode too, or print that command.

### 17. Installer edits shell profiles without listing the lines (Low)

- **Task:** first SDK install (Oct 8).
- **Steps:** ran the installer.
- **Expected:** a list of the lines it will add before editing.
- **Actual:** `.bashrc`, `.zshrc` and `.bash_profile` were edited without showing the changes.
- **Workaround:** reviewed the files afterwards.
- **Suggestion:** print the lines and the files they go into.

### 18. `project generate -o` writes into the given directory (Low)

- **Task:** generate the hello-world app (Oct 8).
- **Steps:** `vega project generate -t helloWorld -n vegahello -o <dir>`.
- **Expected:** `<dir>/vegahello/`.
- **Actual:** files were written directly into `<dir>`, among existing files.
- **Workaround:** point `-o` at a new empty directory.
- **Suggestion:** create `<dir>/<name>`, or refuse a non-empty directory.

### 19. `run-app` right after "ready" says no device (Low)

- **Task:** install the app straight after booting (Oct 8).
- **Steps:** `vega virtual-device start` → "Virtual device ready." → `vega run-app`.
- **Expected:** the app installs.
- **Actual:** "Device not found: No connected Vega devices found"; `vega device list` showed the device a few seconds later.
- **Workaround:** run `vega device list` (or wait) before installing.
- **Suggestion:** have `start` wait until the device is listed, or have `run-app` wait briefly.

### 20. Every build rewrites the checked-in `manifest.toml` (Low)

- **Task:** commit the app after debug builds (Oct 8 on).
- **Steps:** `npm run build:debug`, then `git status`.
- **Expected:** the build leaves source files alone.
- **Actual:** the build appends ~30 auto-detected `[[needs.module]]` entries plus blank lines that grow with every build, so `manifest.toml` always shows as modified.
- **Workaround:** `git checkout app/manifest.toml` after each build.
- **Suggestion:** write the generated manifest into the build output instead of the source tree.

### 21. Window capture fails when the Virtual Device window is off screen (Low)

- **Task:** scripted visual checks with the window-capture workaround from entry 3 (Oct 9).
- **Steps:** `screencapture -l <window id>` while the window was minimized or on another Space.
- **Expected:** a current frame.
- **Actual:** the capture failed or returned a stale frame, and the check had to be redone.
- **Workaround:** `scripts/vvd_screenshot.sh` only looks for on-screen windows and fails clearly; keep the window visible.
- **Suggestion:** fixed by entry 3's suggestion (a device-side screenshot).

### 22. Sample's player exits when a video ends (Low)

- **Task:** test the overlay on a 12 s clip (Oct 10).
- **Steps:** played the clip to the end.
- **Expected:** stay in the player (or loop) while testing.
- **Actual:** the sample navigates back to the details screen when a video ends, kicking the viewer out mid-test.
- **Workaround:** loop the clip on `ended` (`LOOP_CLIP` in `app/src/cleansheet/config.ts`).
- **Suggestion:** a loop option in the sample's player settings.
