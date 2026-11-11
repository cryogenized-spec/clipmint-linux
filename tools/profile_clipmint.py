"""Reproducible, synthetic ClipMint performance profiling (not a pass/fail test).

Usage:
  python tools/profile_clipmint.py --case store --rows 400 --output perf/store.json
  QT_QPA_PLATFORM=offscreen python tools/profile_clipmint.py --case ui --rows 100 --output perf/ui.json

No real clipboard, network, home-directory database or desktop settings are used.
Results are machine-specific observations, not speedup claims or hard thresholds.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import resource
import statistics
import sys
import tempfile
import time

# Invoking tools/profile_clipmint.py makes tools/ sys.path[0]; resolve
# the checkout package explicitly without altering installed modules.
_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))


def milliseconds(fn, samples: int) -> dict[str, float]:
    values = []
    for _ in range(samples):
        t0 = time.perf_counter_ns()
        fn()
        values.append((time.perf_counter_ns() - t0) / 1_000_000)
    ordered = sorted(values)
    return {
        "median_ms": round(statistics.median(values), 3),
        "p95_ms": round(ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))], 3),
        "max_ms": round(max(values), 3),
    }


def make_corpus(store, rows: int) -> float:
    start = time.perf_counter_ns()
    for i in range(rows):
        label = f"Synthetic workshop notebook {i:05d} with blue tulip metrics"
        if i == rows // 2:
            label += " solitaryfoxglove"
        # Index both global and per-bin history; all entries are synthetic.
        bucket = "Personal" if i % 3 == 0 else "Work"
        store.add("text", label.encode("utf-8"), label, bucket)
    return round((time.perf_counter_ns() - start) / 1_000_000, 3)


def bench_store(rows: int, samples: int, root: Path):
    from clipmint.store import ClipStore
    path = root / "history.sqlite3"
    t0 = time.perf_counter_ns()
    store = ClipStore(path, max_unpinned=rows + 50)
    init_ms = round((time.perf_counter_ns() - t0) / 1_000_000, 3)
    try:
        seed_ms = make_corpus(store, rows)
        if store.count("Work") + store.count("Personal") != rows:
            raise RuntimeError("Synthetic seed count differs from requested corpus")
        scenarios = {
            "latest_1000": lambda: store.search("", None),
            "indexed_rare": lambda: store.search("solitaryfoxglove", None),
            "best_match_rare": lambda: store.search("solitaryfoxglove", None, "Best match"),
            "indexed_common": lambda: store.search("blue tulip", None),
            "category_text": lambda: store.search("", None, category="Text"),
        }
        results = {}
        for name, operation in scenarios.items():
            operation()  # warm the query plan and page cache consistently
            results[name] = milliseconds(operation, samples)
        duplicate = f"Synthetic workshop notebook {rows//2:05d} with blue tulip metrics solitaryfoxglove"
        # Dedup has an indexed fingerprint, and must keep the same ID.
        duplicate_id = store.add("text", duplicate.encode(), duplicate,
                                 "Personal" if (rows // 2) % 3 == 0 else "Work")
        if duplicate_id is None:
            raise RuntimeError("Synthetic duplicate insertion rejected")
        results["duplicate_capture"] = milliseconds(
            lambda: store.add("text", duplicate.encode(), duplicate,
                              "Personal" if (rows // 2) % 3 == 0 else "Work"),
            samples,
        )
        store.close()
        t0 = time.perf_counter_ns()
        reopened = ClipStore(path, max_unpinned=rows + 50)
        reopen_ms = round((time.perf_counter_ns() - t0) / 1_000_000, 3)
        reopened.close()
        return {
            "seed_rows": rows, "samples_per_operation": samples,
            "initial_db_open_ms": init_ms, "seed_total_ms": seed_ms,
            "db_reopen_ms": reopen_ms, "operations": results,
        }
    finally:
        if not store.closed:
            store.close()


def bench_ui(rows: int, root: Path):
    # In a separate Python process from --case store, to isolate Qt imports.
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["XDG_SESSION_TYPE"] = "x11"
    from clipmint.store import ClipStore
    store = ClipStore(root / "clipmint" / "history.sqlite3",
                      max_unpinned=rows + 50)
    try:
        make_corpus(store, rows)
    finally:
        store.close()
    t0 = time.perf_counter_ns()
    from PySide6.QtWidgets import QApplication
    from clipmint.app import ClipMintWindow
    imports_ms = round((time.perf_counter_ns() - t0) / 1_000_000, 3)
    t0 = time.perf_counter_ns()
    app = QApplication.instance() or QApplication(["clipmint-perf"])
    qt_init_ms = round((time.perf_counter_ns() - t0) / 1_000_000, 3)
    window = None
    try:
        t0 = time.perf_counter_ns()
        window = ClipMintWindow()
        construct_ms = round((time.perf_counter_ns() - t0) / 1_000_000, 3)
        t0 = time.perf_counter_ns()
        app.processEvents()
        events_ms = round((time.perf_counter_ns() - t0) / 1_000_000, 3)
        # These synthetic navigation timings exercise already-created pages.
        # They do not measure compositor painting or a physical hotkey.
        window.open_section(1)  # prime screenshot gallery once
        window.open_section(2)  # prime recordings list once
        nav = {
            "settings_vault": milliseconds(
                lambda: (window.open_section(5), window.open_section(3)), 30,
            ),
            "screenshots_recordings": milliseconds(
                lambda: (window.open_section(1), window.open_section(2)), 30,
            ),
            "settings_clipboard": milliseconds(
                lambda: (window.open_section(5), window.open_section(0)), 15,
            ),
        }
        return {
            "seed_rows": rows, "imports_ms": imports_ms,
            "qt_application_ms": qt_init_ms, "window_construct_ms": construct_ms,
            "first_event_pass_ms": events_ms,
            "navigation": nav,
            "live_qt_widgets": len(QApplication.allWidgets()),
        }
    finally:
        if window is not None:
            for name in (
                "poller", "_hidden_clipboard_timer", "_auto_update_timer",
                "_temporary_expiry_timer", "_history_search_timer",
                "_vault_lock_timer",
            ):
                timer = getattr(window, name, None)
                if timer is not None:
                    timer.stop()
            window._closing = True
            if not window.store.closed:
                window.store.close()
            window.close()
            window.deleteLater()
        app.processEvents()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=("store", "ui"), required=True)
    parser.add_argument("--rows", type=int, default=400)
    parser.add_argument("--samples", type=int, default=25)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.rows < 10 or args.rows > 10000:
        parser.error("--rows must be between 10 and 10000")
    if args.samples < 5 or args.samples > 1000:
        parser.error("--samples must be between 5 and 1000")
    with tempfile.TemporaryDirectory(prefix="clipmint-synthetic-perf-") as directory:
        root = Path(directory)
        old_env = {
            name: os.environ.get(name)
            for name in ("XDG_DATA_HOME", "XDG_CONFIG_HOME", "HOME")
        }
        # Capture-library builders use Path.home(); keep synthetic profiling
        # strictly within the temporary sandbox, never ~/Pictures or ~/Videos.
        os.environ["HOME"] = str(root)
        os.environ["XDG_DATA_HOME"] = str(root)
        os.environ["XDG_CONFIG_HOME"] = str(root / "config")
        try:
            measurements = (
                bench_store(args.rows, args.samples, root)
                if args.case == "store" else bench_ui(args.rows, root)
            )
        finally:
            for name, value in old_env.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
    result = {
        "scenario": args.case, "platform": platform.platform(),
        "python": platform.python_version(),
        "peak_process_rss_mib": round(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 2
        ),
        "measurements": measurements,
    }
    output = json.dumps(result, sort_keys=True, indent=2)
    print("CLIPMINT_PERFORMANCE_RESULT=" + json.dumps(result, sort_keys=True),
          flush=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
