from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from bluesky.plugins.recording_client import RecordingClient


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps({"state": "RECORDING"}).encode()


class RecordingClientTests(unittest.TestCase):
    @patch("urllib.request.urlopen", return_value=_Response())
    def test_create_run_uses_bearer_auth(self, urlopen):
        client = RecordingClient("http://capture:8000", "secret", retries=0)
        result = client.create_run("20261109_104530_a7b9c2", "demo", {})
        self.assertEqual(result["state"], "RECORDING")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer secret")
        self.assertEqual(request.full_url, "http://capture:8000/api/v1/runs")


if __name__ == "__main__":
    unittest.main()
