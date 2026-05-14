# 2026-05 Cleanup Archive

This folder keeps historical files that were useful during V5.4-V5.6 iteration but
should no longer live in the project root.

## Folders

- `backups/`: old `.bak` snapshots of source and docs.
- `patch-scripts/`: one-off hotfix and migration scripts.
- `design-docs/`: historical planning, implementation, and performance notes.
- `workflow-backups/`: superseded CI workflow files.

These files are retained for traceability. Active development should use the root
source files, the current `README.md`, and `.github/workflows/build.yml`.
