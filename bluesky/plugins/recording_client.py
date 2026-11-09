"""Small authenticated HTTP client for the remote capture service."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


class RecordingClient:
    def __init__(self, base_url: str, token: str, timeout: float = 30.0, retries: int = 5) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.retries = max(0, retries)

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            request = urllib.request.Request(
                self.base_url + path,
                data=body,
                method=method,
                headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                last = exc
                if attempt < self.retries:
                    time.sleep(min(2**attempt, 10))
        raise RuntimeError(f"capture service request failed: {method} {path}: {last}")

    def create_run(self, run_id: str, scenario: str, metadata: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", "/api/v1/runs", {"run_id": run_id, "scenario": scenario, "metadata": metadata})

    def stop(self, run_id: str) -> dict[str, Any]:
        return self.request("POST", f"/api/v1/runs/{run_id}/stop")

    def upload_log(self, run_id: str, path: Path) -> dict[str, Any]:
        import base64
        import hashlib

        content = path.read_bytes()
        return self.request("POST", f"/api/v1/runs/{run_id}/logs", {
            "filename": path.name,
            "content_base64": base64.b64encode(content).decode("ascii"),
            "sha256": hashlib.sha256(content).hexdigest(),
        })

    def finalize(self, run_id: str) -> dict[str, Any]:
        return self.request("POST", f"/api/v1/runs/{run_id}/finalize")

