"""Coordinate an Elgato recording and BlueSky log transfer over HTTP.

Enable the plugin with ``hitl_recording`` in ``settings.cfg``.  The stack
commands are ``RECORDING ON`` and ``RECORDING OFF``.  ``ON`` starts the
remote capture; ``OFF`` closes BlueSky's datalogs, stops the remote capture,
uploads only the current run's logs, and asks the capture service to verify
and publish the run atomically.

The HTTP work runs in a worker thread so simulation callbacks never wait on
the LAN.  A failed run remains visible in the service and can be reconciled
by repeating ``RECORDING OFF`` or by inspecting its run ID.
"""

from __future__ import annotations

import atexit
import secrets
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import bluesky as bs
from bluesky import settings, stack
from bluesky.tools import datalog

from bluesky.plugins.recording_client import RecordingClient

settings.set_variable_defaults(
    video_analysis_api_url="",
    video_analysis_api_token="",
    auto_recording_enabled=False,
    auto_transfer_enabled=True,
    transfer_retry_count=5,
    transfer_timeout_seconds=30.0,
)

coordinator = None


def _run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"{stamp}_{secrets.token_hex(3)}"


class RecordingCoordinator:
    def __init__(self) -> None:
        self.client = RecordingClient(
            settings.video_analysis_api_url,
            settings.video_analysis_api_token,
            settings.transfer_timeout_seconds,
            settings.transfer_retry_count,
        ) if settings.video_analysis_api_url and settings.video_analysis_api_token else None
        self.run_id: str | None = None
        self._worker: threading.Thread | None = None
        self._lock = threading.RLock()

    def start(self) -> tuple[bool, str]:
        with self._lock:
            if self.run_id is not None:
                return False, f"RECORDING already active: {self.run_id}"
            if self.client is None:
                return False, "RECORDING is not configured: set video_analysis_api_url and video_analysis_api_token"
            run_id = _run_id()
            scenario = stack.get_scenname() or "untitled"
            metadata = {"recording_start_utc": datetime.now(timezone.utc).isoformat(), "host": __import__("socket").gethostname()}
            self.run_id = run_id
            self._worker = threading.Thread(target=self._start_worker, args=(run_id, scenario, metadata), daemon=True)
            self._worker.start()
            return True, f"RECORDING start requested: {run_id}"

    def _start_worker(self, run_id: str, scenario: str, metadata: dict) -> None:
        try:
            result = self.client.create_run(run_id, scenario, metadata)
            print(f"[HITL_RECORDING] capture started: {result.get('run_id', run_id)}")
        except Exception as exc:
            print(f"[HITL_RECORDING] capture start failed for {run_id}: {exc}")

    def stop(self, finalize_logs: bool = True, log_dir: Path | None = None) -> tuple[bool, str]:
        with self._lock:
            run_id = self.run_id
            if run_id is None:
                return False, "RECORDING is not active"
            self.run_id = None
            if self._worker is not None and self._worker.is_alive():
                self._worker.join(timeout=5)
        self._worker = threading.Thread(target=self._stop_worker, args=(run_id, finalize_logs, log_dir), daemon=True)
        self._worker.start()
        return True, f"RECORDING stop requested: {run_id}"

    def _stop_worker(self, run_id: str, finalize_logs: bool, log_dir: Path | None = None) -> None:
        try:
            run_dir = log_dir or Path(datalog.getRunDir())
            if finalize_logs:
                # CSVLogger.flushes each row. reset() closes every current-run
                # logger, which is the only reliable finalization boundary.
                datalog.reset()
            self.client.stop(run_id)
            if settings.auto_transfer_enabled:
                for path in sorted(run_dir.glob("*.log")):
                    self.client.upload_log(run_id, path)
                self.client.finalize(run_id)
            print(f"[HITL_RECORDING] run ready: {run_id}")
        except Exception as exc:
            print(f"[HITL_RECORDING] finalization failed for {run_id}: {exc}")

    def close(self) -> None:
        with self._lock:
            run_id = self.run_id
            self.run_id = None
        if run_id is not None:
            # atexit must not delegate the final transfer to a daemon thread
            # that Python will terminate immediately.
            self._stop_worker(run_id, True)


def init_plugin():
    global coordinator
    coordinator = RecordingCoordinator()
    atexit.register(coordinator.close)

    auto_start_checked = False

    def update():
        nonlocal auto_start_checked
        if settings.auto_recording_enabled and not auto_start_checked and bs.sim.state == bs.OP:
            auto_start_checked = True
            coordinator.start()

    @stack.command(name="RECORDING")
    def recording(flag: "onoff" = None):
        if flag is None:
            return True, f"RECORDING is {'ON: ' + coordinator.run_id if coordinator.run_id else 'OFF'}"
        if flag:
            return coordinator.start()
        log_dir = Path(datalog.rundir) if datalog.rundir is not None else Path(datalog.getRunDir())
        datalog.reset()
        return coordinator.stop(finalize_logs=False, log_dir=log_dir)

    config = {"plugin_name": "HITL_RECORDING", "plugin_type": "sim", "update_interval": 0.5, "update": update}
    return config, {}
