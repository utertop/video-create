# Validation Workflow

This project uses a layered validation workflow. The goal is to keep everyday changes fast, while still having a reliable release-level safety net.

## Default Checks

Use this after normal frontend, Tauri command, Python engine, or smoke-test changes:

```powershell
npm.cmd run check
```

This runs:

- frontend TypeScript and Vite build
- Tauri `cargo check`
- Python engine compile check
- Python engine CLI help check
- core smoke tests

## Fast Frontend Check

Use this after small frontend-only changes:

```powershell
npm.cmd run build:web
```

This is the minimum check for React component extraction, TypeScript contract edits, and CSS-free UI refactors.

## Full Release Check

Use this before release-sized changes or risky render-engine work:

```powershell
npm.cmd run check:full
```

This includes the default checks plus diagnostic bundle assertions, Tauri tests, and the broader smoke-test suite.

## Test Artifacts

Smoke tests create temporary project folders under `tests/tmp_vcs_*`. They should not be committed.

Clean generated artifacts:

```powershell
npm.cmd run clean:test-artifacts
```

Preview cleanup:

```powershell
npm.cmd run clean:test-artifacts -- --dry-run
```

## Handling Intermittent Failures

If a check fails with an environment-shaped error, rerun the same command once before changing code. Examples include path casing issues, temporary file access, or tooling startup failures.

`scripts/check.mjs` prints the current working directory, platform, Node, npm, Vite, Python, and Cargo versions at startup. Include that block when reporting a validation failure.

If the same failure repeats twice, treat it as real and investigate before continuing.

## Suggested PR Notes

For each PR or commit-sized change, record:

- commands run
- whether the first run passed
- any rerun needed
- generated artifacts cleaned or intentionally left alone

