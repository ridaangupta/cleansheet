# Friction Log

Every snag with the Vega SDK, Vega Virtual Device, Builder Tools MCP, and AWS services, logged as it happens. This feeds the hackathon friction-log bonus and the product feedback section of the submission.

| Date | Tool | What I was doing | What went wrong | Time lost | Workaround / fix |
| --- | --- | --- | --- | --- | --- |
| 2026-10-08 | Vega SDK installer | Running `get_vvm.sh` with `NONINTERACTIVE=true` | Vega Studio extension was skipped even though VS Code was installed; the installer only printed a Marketplace link | 2 min | `code --install-extension amazon-devices.kepler-studio` |
| 2026-10-08 | Vega SDK installer | First install | Installer edits `.bashrc`, `.zshrc` and `.bash_profile` without listing the exact lines it adds beforehand | 0 | Reviewed the files afterwards |
| 2026-10-08 | Vega Virtual Device | `vega virtual-device start` (first boot) | "Deadline reached (60s) but virtual device unresponsive"; log shows "failed to access shell". The first boot just needs longer than the default timeout | 5 min | `vega virtual-device start -t 300` |
| 2026-10-08 | Vega Virtual Device / vda | Running the hello-world app after boot reported "ready" | `vega device list` and `vega run-app` hung with no output or timeout; `vda shell echo` also hung. A device-info query from boot was stuck | 10 min | Stop the device, kill the stuck `vda` processes, start again; worked on the second boot |
| 2026-10-08 | Vega CLI | `vega project generate -t helloWorld -n vegahello -o <dir>` | Files were written directly into `<dir>`, not `<dir>/vegahello`, scattering them among existing files | 2 min | Point `-o` at an empty directory created for the project |
| 2026-10-08 | Builder Tools MCP | `init-context -a claude-code-cli -f` in a repo that already had CLAUDE.md | Appended ~210 lines of always-on rules to the existing CLAUDE.md and installed a skill globally in `~/.claude/skills` | 5 min | Moved the content into `.claude/amazon-devices-context.md` and imported it from CLAUDE.md |
