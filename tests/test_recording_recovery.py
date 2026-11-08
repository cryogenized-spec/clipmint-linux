"""No silent deletion of unfinished MP4/GIF recordings."""
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import time
from unittest.mock import patch
import unittest

from clipmint.recording_recovery import pending_recordings, resolve_pending, _command_writes_recording


class RecordingRecoveryTests(unittest.TestCase):
    def test_symlinked_directory_writer_argument_is_detected(self):
        with TemporaryDirectory() as home:
            root = Path(home)
            actual = root / "real-video-folder"
            actual.mkdir()
            alias = root / "Videos"
            alias.symlink_to(actual, target_is_directory=True)
            filename = ".pending-recording-20261105-130000-123456.mp4"
            candidate = alias / filename
            candidate.write_bytes(b"still recording")
            process_args = (
                b"/usr/bin/ffmpeg\0-y\0-i\0:0.0\0" +
                os.fsencode(str(candidate)) + b"\0"
            )
            self.assertTrue(_command_writes_recording(process_args, candidate))
            self.assertTrue(_command_writes_recording(
                process_args, actual / filename
            ))
            self.assertFalse(_command_writes_recording(
                b"/usr/bin/other\0" + os.fsencode(str(candidate)) + b"\0",
                candidate,
            ))

    def test_discovery_does_not_mutate_or_follow_symlinks(self):
        with TemporaryDirectory() as home:
            folder = Path(home)
            clip = folder / ".pending-recording-20261105-130000-123456.mp4"
            clip.write_bytes(b"unfinished")
            os.utime(clip, (time.time() - 120, time.time() - 120))
            log = clip.with_suffix(".ffmpeg.log")
            log.write_text("diagnostics")
            (folder / "unrelated.mp4").write_bytes(b"keep")
            (folder / ".pending-recording-20261105-130000-123457.gif").symlink_to(clip)
            # Discovery filtering is tested here; live /proc inspection is
            # deliberately isolated because same-user CI runner processes can
            # disappear or deny cmdline reads at arbitrary points in the scan.
            # Production writer detection remains fail-closed and unchanged.
            with patch("clipmint.recording_recovery._writer_may_be_active", return_value=False):
                self.assertEqual(pending_recordings(folder), [clip])
            self.assertTrue(log.is_file())
            self.assertEqual(clip.read_bytes(), b"unfinished")

    def test_recovery_preserves_bytes_and_avoids_collisions(self):
        with TemporaryDirectory() as home:
            folder = Path(home)
            clip = folder / ".pending-recording-20261105-130000-123456.mp4"
            clip.write_bytes(b"partial MP4 data")
            os.utime(clip, (time.time() - 120, time.time() - 120))
            original = folder / "recovered-recording-20261105-130000-123456.mp4"
            original.write_bytes(b"existing")
            # /proc may be briefly unreadable in shared CI runners, which
            # correctly causes production's conservative writer check to
            # fail closed. Mock that external state in this deterministic
            # filename/bytes test; the active-writer safeguard is tested below.
            with patch("clipmint.recording_recovery._writer_may_be_active",
                       return_value=False):
                recovered = resolve_pending(clip, "recover")
            self.assertEqual(recovered.name, "recovered-recording-20261105-130000-123456-1.mp4")
            self.assertEqual(recovered.read_bytes(), b"partial MP4 data")
            self.assertEqual(original.read_bytes(), b"existing")
            self.assertFalse(clip.exists())

    def test_discard_is_explicit_and_removes_associated_log_only(self):
        with TemporaryDirectory() as home:
            folder = Path(home)
            clip = folder / ".pending-recording-20261105-130000-123456.gif"
            clip.write_bytes(b"partial GIF")
            os.utime(clip, (time.time() - 120, time.time() - 120))
            log = clip.with_suffix(".ffmpeg.log")
            log.write_text("ffmpeg")
            keep = folder / "my-other-video.mp4"
            keep.write_bytes(b"keep")
            with self.assertRaises(ValueError):
                resolve_pending(clip, "unknown")
            with patch("clipmint.recording_recovery._writer_may_be_active", return_value=True):
                with self.assertRaisesRegex(ValueError, "still be in use"):
                    resolve_pending(clip, "discard")
                self.assertTrue(clip.exists())
            with patch("clipmint.recording_recovery._writer_may_be_active",
                       return_value=False):
                self.assertIsNone(resolve_pending(clip, "discard"))
            self.assertFalse(clip.exists())
            self.assertFalse(log.exists())
            self.assertTrue(keep.exists())


if __name__ == "__main__":
    unittest.main()
