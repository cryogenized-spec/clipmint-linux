"""Explicit owner for ClipMint's repeating Qt timers.

The window owns each timer's QObject lifetime. This class makes shutdown of
every registered timer deterministic and idempotent, without starting timers,
touching persistence or introducing background threads.
"""
from __future__ import annotations


class RuntimeTimers:
    def __init__(self, **timers):
        self._timers = tuple(timers.items())
        self._stopped = False

    def stop_all(self) -> None:
        if self._stopped:
            return
        # Stop every timer, even if an individual timer raises. The window
        # can then surface the error rather than leaving watchers running.
        errors = []
        for name, timer in self._timers:
            try:
                timer.stop()
            except Exception as exc:
                errors.append((name, exc))
        if errors:
            first, exc = errors[0]
            raise RuntimeError(
                f"Could not stop background timer '{first}'"
            ) from exc
        self._stopped = True
