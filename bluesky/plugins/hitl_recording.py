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
import json
import secrets
import time
import threading
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


def _start_automatic_loggers(run_id: str) -> Path:
    """Start all five loggers for the current scenario run.

    The logger plugins must already be enabled in settings.cfg. Starting the
    CSVLogger objects directly avoids queueing commands into the simulation
    stack and means the first automatic run does not depend on an operator
    entering ON commands.
    """
    from bluesky.plugins import hitl_conflog, hitl_fovaclog, hitl_heartbeatlog, hitl_opcmdlog

    loggers = (
        hitl_fovaclog.fovlog,
        hitl_opcmdlog.cmdlog,
        hitl_heartbeatlog.heartbeatlog.logger,
        hitl_conflog.hitlconflog.logger,
    )
    if any(logger is None for logger in loggers):
        raise RuntimeError("automatic logging requires FOVACLOG, OPCMDLOG, HEARTBEATLOG and HITLCONFLOG plugins")
    names = ('FOVACLOG', 'OPCMDLOG', 'HEARTBEATLOG', 'HITLCONFLOG')
    for name, logger in zip(names, loggers):
        if not logger.isopen():
            logger.start()
            print(f'[HITL_RECORDING] run_id={run_id} logger={name} action=start filename={logger.fname}')
        else:
            print(f'[HITL_RECORDING] run_id={run_id} logger={name} action=already_open filename={logger.fname}')
    hitl_conflog.hitlconflog.prevconf = set()
    # Do not reset the view tracker here. The simulator client sends the
    # actual radar pan/zoom/aspect-ratio snapshot during scenario loading;
    # resetting it at automatic recording start loses that snapshot and makes
    # FOVACLOG use the default square viewport.
    return Path(datalog.rundir)


def _external_screenrec_start(capture_start_epoch: float) -> None:
    """Enable SCREENRECLOG without starting BlueSky's local video recorder."""
    from bluesky.plugins import hitl_screenrec

    if hitl_screenrec.screenrec is None:
        raise RuntimeError("HITL_SCREENREC plugin is required for external synchronization logging")
    ok, message = hitl_screenrec.screenrec.start_external(capture_start_epoch)
    if not ok:
        raise RuntimeError(message)
    print(f'[HITL_RECORDING] external SCREENRECLOG action=start filename={hitl_screenrec.screenrec.logger.fname}')


class RecordingCoordinator:
    def __init__(self) -> None:
        self.client = RecordingClient(
            settings.video_analysis_api_url,
            settings.video_analysis_api_token,
            settings.transfer_timeout_seconds,
            settings.transfer_retry_count,
        ) if settings.video_analysis_api_url and settings.video_analysis_api_token else None
        self.run_id: str | None = None
        self.log_dir: Path | None = None
        self.capture_start_epoch: float | None = None
        self.capture_start_failed = False
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
            self.log_dir = _start_automatic_loggers(run_id)
            self.capture_start_epoch = None
            self.capture_start_failed = False
            self._worker = threading.Thread(target=self._start_worker, args=(run_id, scenario, metadata), daemon=True)
            self._worker.start()
            return True, f"RECORDING start requested: {run_id}"

    def _start_worker(self, run_id: str, scenario: str, metadata: dict) -> None:
        try:
            result = self.client.create_run(run_id, scenario, metadata)
            acknowledged = result.get("recording_start_utc")
            if acknowledged:
                self.capture_start_epoch = datetime.fromisoformat(acknowledged).timestamp()
            print(f"[HITL_RECORDING] capture started: {result.get('run_id', run_id)}")
        except Exception as exc:
            self.capture_start_failed = True
            print(f"[HITL_RECORDING] capture start failed for {run_id}: {exc}")

    def activate_external_sync_if_ready(self) -> None:
        with self._lock:
            epoch = self.capture_start_epoch
            failed = self.capture_start_failed
        if epoch is not None:
            try:
                _external_screenrec_start(epoch)
                with self._lock:
                    self.capture_start_epoch = None
            except Exception as exc:
                print(f"[HITL_RECORDING] external synchronization logger failed: {exc}")
        elif failed:
            return

    def stop(self, finalize_logs: bool = True, log_dir: Path | None = None) -> tuple[bool, str]:
        with self._lock:
            run_id = self.run_id
            if run_id is None:
                return False, "RECORDING is not active"
            self.run_id = None
            saved_log_dir = self.log_dir
            self.log_dir = None
            if self._worker is not None and self._worker.is_alive():
                self._worker.join(timeout=5)
        self._worker = threading.Thread(
            target=self._stop_worker,
            args=(run_id, finalize_logs, log_dir or saved_log_dir),
            daemon=True,
        )
        self._worker.start()
        return True, f"RECORDING stop requested: {run_id}"

    def _stop_worker(self, run_id: str, finalize_logs: bool, log_dir: Path | None = None) -> None:
        try:
            run_dir = log_dir or Path(datalog.getRunDir())
            if finalize_logs:
                # CSVLogger.flushes each row. reset() closes every current-run
                # logger, which is the only reliable finalization boundary.
                datalog.reset()
            for path in sorted(run_dir.glob('*.log')):
                print(f'[HITL_RECORDING] run_id={run_id} logger={path.stem.split("_")[0]} action=closed filename={path}')
            self.client.stop(run_id)
            if settings.auto_transfer_enabled:
                for path in sorted(run_dir.glob("*.log")):
                    self.client.upload_log(run_id, path)
                finalized = self.client.finalize(run_id)
                video_path = run_dir / f"{run_id}.mp4"
                self.client.download_video(run_id, video_path)
                metadata_path = run_dir / "metadata.json"
                if not metadata_path.exists():
                    finalized["local_video_filename"] = video_path.name
                    finalized["local_video_size"] = video_path.stat().st_size
                    metadata_path.write_text(json.dumps(finalized, indent=2), encoding="utf-8")
            print(f"[HITL_RECORDING] remote run ready: {run_id}; local logs retained, video remains on capture host")
        except Exception as exc:
            print(f"[HITL_RECORDING] finalization failed for {run_id}: {exc}")

    def close(self) -> None:
        with self._lock:
            run_id = self.run_id
            log_dir = self.log_dir
            self.run_id = None
            self.log_dir = None
            start_worker = self._worker
        if start_worker is not None and start_worker.is_alive():
            start_worker.join(timeout=5)
        if run_id is not None:
            # Close loggers before synchronously completing the transfer. This
            # is the explicit shutdown boundary; atexit is only a fallback.
            datalog.reset()
            self._stop_worker(run_id, False, log_dir)


def init_plugin():
    global coordinator
    coordinator = RecordingCoordinator()
    atexit.register(coordinator.close)

    # QUIT is the normal simulation shutdown path. Wrap it so transfer is
    # completed before the simulation process is allowed to exit; atexit is
    # retained only as a last-resort fallback for process termination paths.
    original_quit = bs.sim.quit

    def quit_with_recording(*args, **kwargs):
        coordinator.close()
        return original_quit(*args, **kwargs)

    bs.sim.quit = quit_with_recording

    auto_start_checked = False

    def update():
        nonlocal auto_start_checked
        if coordinator is not None:
            coordinator.activate_external_sync_if_ready()
        if settings.auto_recording_enabled and not auto_start_checked and bs.sim.state == bs.OP:
            auto_start_checked = True
            ok, message = coordinator.start()
            if not ok:
                print(f'[HITL_RECORDING] automatic start failed: {message}')

    def reset():
        """Close the previous run when a scenario is loaded/reset.

        HOLD is intentionally not handled here. A reset is the lifecycle
        boundary BlueSky uses for scenario loading; transfer runs in the
        coordinator worker so the simulation loop is not blocked.
        """
        nonlocal auto_start_checked
        auto_start_checked = False
        if coordinator is None or coordinator.run_id is None:
            return
        run_id = coordinator.run_id
        log_dir = coordinator.log_dir
        datalog.reset()
        ok, message = coordinator.stop(finalize_logs=False, log_dir=log_dir)
        if not ok:
            print(f'[HITL_RECORDING] reset finalization skipped for {run_id}: {message}')

    @stack.command(name="RECORDING")
    def recording(flag: "onoff" = None):
        if flag is None:
            return True, f"RECORDING is {'ON: ' + coordinator.run_id if coordinator.run_id else 'OFF'}"
        if flag:
            return coordinator.start()
        log_dir = Path(datalog.rundir) if datalog.rundir is not None else Path(datalog.getRunDir())
        datalog.reset()
        return coordinator.stop(finalize_logs=False, log_dir=log_dir)

    config = {
        "plugin_name": "HITL_RECORDING",
        "plugin_type": "sim",
        "update_interval": 0.5,
        "update": update,
        "reset": reset,
    }
    return config, {}
