# Installer Test Checklist

Use this checklist before publishing a Windows PC build.

## Build

- [ ] Run `npm run check:full`.
- [ ] Run `npm run build:desktop`.
- [ ] Confirm the installer exists under `src-tauri/target/release/bundle/nsis/`.
- [ ] Run `npm run verify:worker-packaged`.

## Install

- [ ] Install `Video Create Studio_<version>_x64-setup.exe` on a clean Windows user account if available.
- [ ] Confirm Start Menu entry is created.
- [ ] Launch the app from the Start Menu.
- [ ] Confirm startup self-check passes.
- [ ] Confirm the bundled worker health check passes in the UI.

## First Project

- [ ] Select a small素材 folder with 3-5 images.
- [ ] Select a writable output folder.
- [ ] Run intelligent arrangement.
- [ ] Review the story blueprint.
- [ ] Confirm and generate `render_plan.json`.
- [ ] Confirm render preflight passes.
- [ ] Generate a low-resolution preview.
- [ ] Start final render.
- [ ] Confirm the output MP4 exists and can be opened.
- [ ] Confirm "Open output folder" works.

## Recent Project

- [ ] Close and reopen the app.
- [ ] Confirm the previous project appears under recent projects.
- [ ] Restore the recent project.
- [ ] Confirm input folder, output folder, title, and output filename are restored.

## Failure Cases

- [ ] Move or delete one source asset after compiling the render plan.
- [ ] Start final render and confirm preflight blocks rendering with a clear missing-file message.
- [ ] Choose a read-only output directory if available and confirm preflight reports a write-permission issue.
- [ ] Cancel a running render and confirm the UI shows a cancelled state.

## Uninstall

- [ ] Uninstall from Windows Settings.
- [ ] Confirm the app is removed from the Start Menu.
- [ ] Confirm user-created output files are not deleted.

