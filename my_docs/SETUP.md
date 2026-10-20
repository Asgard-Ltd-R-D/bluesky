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

## Enable HITL loggers (new machine)

`settings.cfg` is gitignored, so on a fresh clone it is generated from the
defaults without the HITL loggers. After the first run, edit `settings.cfg`
in the project root and replace the `enabled_plugins` line with:

```python
enabled_plugins = ['area', 'datafeed', 'hitl_fovaclog', 'hitl_opcmdlog', 'hitl_heartbeatlog']
```

Restart BlueSky and check with `PLUGIN LIST`. `HITL_CONFLOG` is not needed
here — the scenarios in `scenario/hitl_test/` load it with `PLUGIN LOAD HITL_CONFLOG`.

## Deactivate virtual environment

```bash
deactivate
```
