# ClipMint architecture audit — 11 November 2026

**Status:** Architecture refactoring ready to conclude **conditionally on PR CI and merged-main integration tests**. This is an engineering architecture review, not an independent security audit, a claim of verified end-user performance, or a Linux Mint field-test report.

**Scope and evidence:** Reviewed the repository's application/Qt ownership, SQLite persistence, encrypted history, clipboard ingestion/egress, background OCR and update workers, screenshots/FFmpeg recording and packaging/CI contracts. Baseline source: `main` commit `617d86369e39ac72a5a88bf13e02efcda522e971` (PR #89); this audit accompanies the final copy-boundary refactor. Before that PR, GitHub CI ran **398 tests (5 skipped), zero failures** and passed X11 cross-process clipboard, performance/visual baselines and Debian installer smoke tests. The current PR and subsequent combined-main results must be checked separately before declaring the audit gates satisfied.

## Architecture and resource ownership

| Boundary | Owner | Integration contract |
| --- | --- | --- |
| Linux X11 entry point / single instance | `app.main`, `single_instance.InstanceServer` | Acquire owner-only IPC lock **before** opening the window/database; hand the server to the window; explicitly close it on Quit or failed initialization |
| Qt app and window | `ClipMintWindow`, `AppLifecycleMixin` | Initializes services/controllers; close-to-background retains the clipboard watcher; explicit Quit ends it; active recording refuses Quit |
| Background timers | `RuntimeTimers` | Owns six registered timer shutdowns; attempts all stops and reports failures without stranding the database or IPC lock |
| Incoming clipboard | `ClipboardMonitorMixin` | X11 polling/signals, own-write guard and privacy exclusion; only validated data reaches `ClipboardIngestionService` |
| Clipboard persistence routing | `ClipboardIngestionService` | Explicit router and **live** store provider, so enabling encrypted history cannot leave a stale plaintext-store reference |
| Outgoing saved history | `history_clipboard_copy.copy_saved_clip` | One MIME/plain copy boundary for main window, queue and popup; lazy clipboard/guard access; refresh Temporary copy time only after successful write |
| Secret clipboard copies | `VaultControllerMixin` | **Separate** path; never use saved-history copy or persist vault credentials as ordinary clips |
| SQLite and indexes | `ClipStore`, `HistorySearchService`, `ClipSearchIndex` | One store-owned connection shared with search; UI uses public store operations |
| SQL schema / old schema compatibility | `history_schema.initialize_history_schema` | Idempotent upgrades; SAVEPOINT rollback for legacy MIME CHECK; preserves IDs, pins, timestamps, bins and metadata |
| Retention and compaction | `HistoryRetentionService` | Same connection/index; byte cap and Temporary expiry are default-off, opt-in; pinned entries protected |
| Encrypted history | `EncryptedClipStore`, `HistorySecurityControllerMixin` | Explicit desktop-keyring opt-in; encrypted payloads; no plaintext FTS; legacy plaintext copy preserved until verified user-authorized deletion |
| OCR | `OcrWorker`, `OcrControllerMixin` | Offline bounded PNG and text; parent-owned QThread; explicit Quit defers until worker completion; late results suppressed |
| Screen/video capture | `ScreenshotCaptureControllerMixin`, `RecordingControllerMixin`, `RegionRecorder` | Explicit selection/recording transitions; incomplete recordings recovered/discarded by user choice |
| Updates and installers | `UpdateControllerMixin`, `updater.py`, GitHub Actions | Manual check never downloads; automatic small patches require opt-in; large installer downloads require confirmation; native Mint package manager approves installation |

## Regression safety gates

1. **Automated tests:** Python/Qt test suite, Xvfb cross-process clipboard round-trip, legacy SQLite migrations, encrypted-history and retention edge cases, OCR worker shutdown, failed startup cleanup, shared copy semantics and no implicit auto-update opt-in.
2. **Visual verification:** Native Crimson Archive and actual Qt window captures; show/hide, screenshot and preview behavior exercised by existing UI smoke tests.
3. **Installer verification:** Frozen executable launch under virtual X11; SHA-256 verified ancillary assets, published-preview patch decoder test, `.deb` package construction and installed-package smoke test.
4. **Architecture guards:** `tests/test_architecture_boundaries.py` checks the single copy path, lock-before-window bootstrap, UI-independent data services and vault-copy separation.

## Residual risks and deliberate limits

| Severity | Remaining concern | Handling |
| --- | --- | --- |
| High for credential use | The experimental vault has **not received an independent security audit**; X11 clipboard contents can be read by other local applications | Keep the existing README warning; do not market the vault as a password-manager replacement |
| Medium | Encrypted history search may synchronously inspect/decrypt a bounded set of entries on the Qt main thread; SQLite writes and large media can block responsiveness | Dedicated performance phase: profile on actual Linux Mint hardware, then offload bounded tasks without relaxing encryption |
| Medium | Update checks/downloads use daemon Python threads and queued Qt signals; they are not cooperatively cancellable at shutdown | Future change only if traces show a real exit/resource problem; preserve user consent and network budgets |
| Medium | Delayed one-shot screenshot/recording callbacks can outlive an initiated Quit and are not centrally registered like repeating timers | Audit each callback's `_closing` guard when revisiting capture lifecycles; do not silently weaken screenshot behavior |
| Medium | `ClipMintWindow` still composes multiple controller mixins sharing Qt widget state | Accept for this iteration: extracted data/service boundaries are explicit; don't mechanically split mixins without a measured reliability benefit |
| Operational | A real Linux Mint Cinnamon/X11 environment, multi-monitor coordinate variations, display scaling and keyboard interactions are only partially modeled by CI/Xvfb | Perform real-device acceptance tests; CI is not a substitute for that |
| Operational | Published preview packaging depends on third-party asset availability in GitHub runners; unit tests cannot guarantee network reachability | Keep pinned hashes, release checksums and verified installer gate |

## Decision and next phase

**Architecture stopping rule:** No known duplicate saved-history clipboard copy implementation remains; database schema, retention, search and clipboard ingestion have explicit shared-connection/service boundaries; normal Quit and failed startup release resources deterministically; opt-in/privacy rules remain unchanged. Further class decomposition alone is not a performance objective.

**Next phase (measured performance):** Baseline on the user's Linux Mint laptop using the existing synthetic profiler plus real startup traces; distinguish Python import time from Qt window construction, encrypted search latency, clipboard watcher activity and memory/CPU pressure. Profile first, optimize only demonstrated bottlenecks, rerun the same test and installer gates, and compare improvements with repeatable measurements.

**Sign-off rule:** Mark the final architecture pass integrated only after all checks on its pull request pass and the change is merged; then confirm merged-main integration CI separately. Do not claim local installation or user-device speed improvements from GitHub runner metrics.
