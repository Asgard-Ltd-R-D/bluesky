from __future__ import annotations

import hashlib
import unittest
from pathlib import Path
from unittest.mock import patch

from bluesky.plugins.recording_client import RecordingClient


class _Response:
    def __init__(self, chunks: list[bytes]) -> None:
        self.headers = {"X-Content-SHA256": hashlib.sha256(b"".join(chunks)).hexdigest()}
        self._chunks = iter(chunks)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size: int) -> bytes:
        return next(self._chunks, b"")


class _Temporary:
    name = "capture.part"

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def write(self, content: bytes) -> int:
        return len(content)


class VideoDownloadTests(unittest.TestCase):
    def test_video_download_streams_checksum_and_renames_atomically(self) -> None:
        client = RecordingClient("http://capture", "token", retries=0)
        response = _Response([b"first", b"second"])
        with patch("bluesky.plugins.recording_client.urllib.request.urlopen", return_value=response), \
             patch("bluesky.plugins.recording_client.tempfile.NamedTemporaryFile", return_value=_Temporary()), \
             patch("bluesky.plugins.recording_client.os.replace") as replace, \
             patch.object(Path, "exists", return_value=False):
            result = client.download_video("run_123456", Path("capture.mp4"))
        self.assertEqual(result["size"], 11)
        self.assertEqual(result["sha256"], hashlib.sha256(b"firstsecond").hexdigest())
        replace.assert_called_once()

    def test_video_download_does_not_overwrite_existing_file(self) -> None:
        client = RecordingClient("http://capture", "token", retries=0)
        with patch.object(Path, "exists", return_value=True):
            with self.assertRaises(FileExistsError):
                client.download_video("run_123456", Path("capture.mp4"))


if __name__ == "__main__":
    unittest.main()
