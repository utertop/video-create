# Telemetry Privacy Notice `telemetry-consent-2026-05-v1`

This notice applies to the optional telemetry and remote crash reporting flow introduced in the `2026-05` consent version.

## What it is for

This telemetry exists to help the product team answer product maturity questions such as:

- crash-free session rate
- first export success rate
- most common error codes
- which support queue a failure belongs to
- whether `resume / retry / partial reuse` is actually helping users recover renders

## What is collected locally

When a user enables anonymous telemetry, the app can store:

- session start / clean exit / crash recovery markers
- startup, preflight, render, and frontend runtime event types
- error codes
- support queue
- severity
- anonymous tags
- render recovery labels such as resumable or retryable

## What is not collected

This telemetry does not include:

- media file contents
- rendered video contents
- project title text
- end text or watermark text
- raw user prompts
- source media paths as telemetry labels

Diagnostic bundles are different from telemetry and may still contain paths or logs when the user explicitly exports them for support.

## Optional remote upload

Remote upload is a second opt-in layer on top of local telemetry.

If the user configures a remote endpoint and enables remote upload, the app may send:

- app version
- consent version
- anonymous event labels
- error code
- support queue
- severity
- recovery labels

Remote upload should use `https` in production. `http` is allowed only for `localhost` development endpoints.

## User controls

Users can:

- keep telemetry disabled
- enable local anonymous telemetry only
- enable remote upload later
- clear local telemetry history
- disable telemetry at any time

## Support and diagnostics

Support should treat telemetry as aggregate stability evidence, not as a replacement for a user-exported diagnostic bundle.
