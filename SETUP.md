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

## Deactivate virtual environment

```bash
deactivate
```
