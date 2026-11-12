# BlueSky Setup & Run Commands

## Create virtual environment

```bash
python3 -m venv venv
```

## Activate virtual environment

```bash
# macOS / Linux
source venv/bin/activate

# Windows
venv\Scripts\activate
```

## Install dependencies

```bash
pip install -e .

# with optional extras (pick what you need)
pip install -e ".[pygame]"
pip install -e ".[qt6]"
pip install -e ".[console]"

# needed for the HITL screen recorder (SCREENREC) - bundles an ffmpeg binary
pip install imageio-ffmpeg
```

## Update dependencies

```bash
pip install --upgrade -e .
pip list --outdated
```

## Run BlueSky

```bash
python BlueSky.py
```

## Configure remote Elgato recording

For the two-computer recording workflow, edit `settings.cfg` in the BlueSky
project root. Add or update the remote capture settings below. Replace the URL
with the LAN address of the computer running Video Analysis System, and replace
the token placeholder with the same secret configured as `CAPTURE_API_TOKEN`
on that computer.

```ini
# Remote Elgato capture coordinator.
video_analysis_api_url = 'http://<VIDEO_ANALYSIS_COMPUTER_IP>:8000'
video_analysis_api_token = '<CAPTURE_API_TOKEN>'
auto_recording_enabled = True
auto_transfer_enabled = True
external_capture_enabled = True
transfer_retry_count = 5
transfer_timeout_seconds = 30.0
```

For the current LAN setup, the URL value is:

```ini
video_analysis_api_url = 'http://192.168.3.2:8000'
```

Keep the real token only in the local configuration file. Do not copy it into
this documentation or commit it to source control. The complete remote
recording protocol and API call sequence is documented in
[REMOTE_RECORDING.md](REMOTE_RECORDING.md).

The capture service must already be running before BlueSky starts automatic
recording. When `auto_recording_enabled = True`, the `HITL_RECORDING` plugin
starts a remote run when the simulation enters operate mode. You can also use
the stack commands manually:

```text
RECORDING ON
RECORDING OFF
```

The remote service stores the Elgato MP4 and receives the BlueSky logs. BlueSky
retains its original log files in its local output directory.

## Enable HITL loggers (new machine)

`settings.cfg` is gitignored, so on a fresh clone it is generated from the
defaults without the HITL loggers. After the first run, edit `settings.cfg`
in the project root and replace the `enabled_plugins` line with:

```python
enabled_plugins = ['area', 'datafeed', 'hitl_fovaclog', 'hitl_opcmdlog', 'hitl_heartbeatlog', 'hitl_screenrec']
```

Restart BlueSky and check with `PLUGIN LIST`. `HITL_CONFLOG` is not needed
here — the scenarios in `scenario/hitl_test/` load it with `PLUGIN LOAD HITL_CONFLOG`.

The logs are buffered and only written to disk when the run ends cleanly: by
loading the next scenario, typing `QUIT`, or closing the window. Killing
the process (`Stop-Process`, Task Manager, closing the terminal) leaves
0-byte log files.

## Deactivate virtual environment

```bash
deactivate
```
