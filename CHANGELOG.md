# ClipMint changelog

This document describes what actually shipped or is being prepared; release-specific files and sizes are authoritative on [GitHub Releases](https://github.com/cryogenized-spec/clipmint-linux/releases).

## Unreleased — v0.6.1 hardening

- Reliability: repair the recorder cancellation controls and add regression coverage (tracked separately from this documentation change).
- Supply chain: move GitHub Action references to immutable SHAs, narrow review-workflow permissions, and stop automated commits of screenshot/base64 artifacts (tracked separately).
- Maintenance: replace the historical README with current usage, privacy, packaging and data-cost guidance.
- Planned, **not yet complete**: independent release signatures, reproducible dependency resolution, live X11/FFmpeg recording verification, and modularization of the main Qt window.

An entry under **Unreleased** is not a claim that a published preview already includes the change. Follow each linked PR and published release.

## Preview 252.1 — 2026-11-08

- Published a version-pinned standalone Preview 227.1 bootstrap script, matching `BOOTSTRAP-SHA256SUMS` and a verified small `.clipdelta` patch.
- Published separate patch manifests for matching previous-preview and Preview 227.1 bases.
- Corrected the Python-only BSDIFF decoder and tested a real release package reconstruction.
- Does **not** provide independent release authentication; the hash checks and installer originate from the same GitHub account.

## Preview 247.1 — 2026-11-08

- Published verified file-aware differential patches, including a patch from Preview 227.1, with SHA-256 verification of the reconstructed installer.

## Earlier 0.6 development

- Introduced clipboard history, search and category filtering, screenshot workflows, recording UI, optional encryption, and a vault.
- Accelerated hidden-window screenshot shortcuts using a lightweight local launcher.
- Introduced update discovery, data-cost guardrails and exact-version package verification.

For the precise code history, see the repository's [commits](https://github.com/cryogenized-spec/clipmint-linux/commits/main/) and [merged pull requests](https://github.com/cryogenized-spec/clipmint-linux/pulls?q=is%3Apr+is%3Amerged).
