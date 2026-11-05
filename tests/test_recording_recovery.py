"""No silent deletion of unfinished MP4/GIF recordings."""
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import time
from unittest.mock import patch
import unittest

from clipmint.recording_recovery import pending_recordings, resolve_pending


class RecordingRecoveryTests(unittest.TestCase):
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
            self.assertIsNone(resolve_pending(clip, "discard"))
            self.assertFalse(clip.exists())
            self.assertFalse(log.exists())
            self.assertTrue(keep.exists())


if __name__ == "__main__":
    unittest.main()
