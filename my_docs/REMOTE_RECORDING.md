# Remote Elgato Capture and BlueSky Log Transfer

This checkout can coordinate BlueSky with a separate Video Analysis System
capture service over HTTP. BlueSky runs on the simulator computer; the Video
Analysis System runs on the computer connected to the Elgato capture device.

The video path and the log-transfer path are separate:

```text
BlueSky computer                         Capture computer
----------------                         ----------------
BlueSky HDMI output  ── HDMI ──────────> Elgato HDMI input
                                         Elgato ── USB ──> capture service

BlueSky recording client ── HTTP/LAN ──> FastAPI capture service
                                      ├─ starts/stops recording
                                      ├─ stores the MP4
                                      └─ receives BlueSky log uploads
```

The remote service must be running before a recording is started. The API is
authenticated with the shared bearer token configured on both computers.

## BlueSky lifecycle

The `HITL_RECORDING` plugin is enabled through `settings.cfg`.

When automatic recording is enabled and the simulation enters operate mode,
the plugin:

1. Generates a unique `run_id`.
2. Starts the enabled BlueSky loggers for the current run.
3. Sends `POST /api/v1/runs` to the capture service.
4. Starts external `SCREENRECLOG` synchronization metadata after the remote
   capture acknowledgment is received.

The plugin also supports the stack command:

```text
RECORDING ON
RECORDING OFF
```

`RECORDING ON` starts a new remote run. `RECORDING OFF` closes/finalizes the
current BlueSky loggers, stops the remote capture, uploads the generated log
files, and asks the remote service to finalize the run.

Normal BlueSky shutdown calls the same finalization path. Log files remain on
the BlueSky computer under the BlueSky output run directory.

The legacy local BlueSky screen recorder should not be used for this workflow:
the `SCREENRECLOG` plugin is used for synchronization metadata, while the
Elgato service owns the captured video.

## API calls made by BlueSky

All requests include:

```http
Authorization: Bearer <CAPTURE_API_TOKEN>
Content-Type: application/json
```

### Start a run

```http
POST /api/v1/runs
```

Example request body:

```json
{
  "run_id": "20261111_113014_ae0d85",
  "scenario": "1con_easy",
  "metadata": {
    "recording_start_utc": "2026-11-11T11:30:14+00:00",
    "host": "BLUESKY-PC"
  }
}
```

The service starts the capture and returns run information, including the
remote recording start timestamp used by BlueSky for synchronization.

### Stop the remote recording

```http
POST /api/v1/runs/{run_id}/stop
```

The capture service stops the Elgato recording and finalizes the MP4 before
the logs are published as a completed input run.

### Upload each BlueSky log

```http
POST /api/v1/runs/{run_id}/logs
```

The current client uploads each `.log` file separately using a JSON body:

```json
{
  "filename": "FOVACLOG_1con_easy_20261111_13-30-15.log",
  "content_base64": "<base64 file contents>",
  "sha256": "<sha256 checksum>"
}
```

The upload is authenticated, checksum-checked, and retried according to the
configured retry and timeout settings. Original BlueSky files are not deleted.

The expected automatic log set is:

```text
FOVACLOG_*.log
HEARTBEATLOG_*.log
HITLCONFLOG_*.log
OPCMDLOG_*.log
SCREENRECLOG_*.log
```

### Finalize and verify the run

```http
POST /api/v1/runs/{run_id}/finalize
```

The service verifies the finalized capture and required logs before making the
run ready in its input directory.

### Inspect a run

```http
GET /api/v1/runs/{run_id}
```

This is useful for checking whether a run is recording, stopped, transferring,
failed, or ready.

### Capture service health and status

```http
GET /api/v1/health
GET /api/v1/capture/status
GET /api/v1/capture/devices
```

`/health` is unauthenticated. Capture status and device discovery require the
bearer token.

## HTTP status meanings

| Status | Meaning |
|---:|---|
| 200 | Health, status, upload, or finalization succeeded |
| 201 | Run was created and recording started |
| 400 | Invalid upload data, filename, checksum, or request |
| 401 | Missing or incorrect bearer token |
| 404 | Run does not exist |
| 409 | Invalid lifecycle transition or incomplete run |
| 503 | Capture service or capture device is unavailable |

The BlueSky client retries network and timeout failures using bounded
exponential backoff. It does not silently treat a failed start or transfer as
successful.

## Required network configuration

On the BlueSky computer, set the capture computer's reachable LAN address:

```ini
video_analysis_api_url = 'http://<CAPTURE_COMPUTER_IP>:8000'
video_analysis_api_token = '<same token as CAPTURE_API_TOKEN on the capture computer>'
```

The capture computer must allow inbound TCP port `8000` through Windows
Firewall when the capture service is configured to use that port. If the
service is bound to another port, use that port in the URL and firewall rule.

## Troubleshooting the connection

From the BlueSky computer:

```powershell
ping <CAPTURE_COMPUTER_IP>
Invoke-WebRequest -Uri 'http://<CAPTURE_COMPUTER_IP>:8000/api/v1/health'
```

To test an authenticated endpoint:

```powershell
$headers = @{ Authorization = 'Bearer <CAPTURE_API_TOKEN>' }
Invoke-WebRequest `
  -Uri 'http://<CAPTURE_COMPUTER_IP>:8000/api/v1/capture/status' `
  -Headers $headers
```

- `Connection refused` usually means the service is stopped or listening on a
  different port.
- A timeout usually indicates an incorrect IP address, firewall rule, or LAN
  routing problem.
- `401 Unauthorized` means the token differs between the two computers.
- `409 Conflict` means the requested run operation is invalid for its current
  lifecycle state.
- `404 Not Found` usually means the `run_id` is wrong or the run was never
  created on the capture computer.

## Security note

Treat the API token as a secret. Do not commit it to documentation, source
control, screenshots, or support messages. Put the token in the local
`settings.cfg` and capture-service environment configuration only, and rotate
it if it has been exposed.
