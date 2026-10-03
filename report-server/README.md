# Dannify report server

Receives the problem reports sent from the app (Settings → About → Report a
problem) and keeps them for you to read. One small Python service; reports are
plain files on disk.

## Run it

```
pip install -r requirements.txt
REPORT_ADMIN_TOKEN=<a long random string> uvicorn server:app --host 0.0.0.0 --port 8080
```

Or with Docker:

```
docker build -t dannify-reports .
docker run -d -p 8080:8080 -e REPORT_ADMIN_TOKEN=<token> -v dannify-reports:/data dannify-reports
```

Any host that runs a container works (a small VPS, Render, Fly.io, Railway).
It must be reachable over **HTTPS** (put it behind the host's TLS or a reverse
proxy such as Caddy).

| Variable | |
|---|---|
| `REPORT_ADMIN_TOKEN` | Required. Protects the reading side. |
| `REPORT_DATA_DIR` | Where reports go (default `./data`, `/data` in the container). |
| `REPORT_NOTIFY_URL` | Optional Discord or Slack webhook, told about each new report. |
| `REPORT_MAX_PER_HOUR` | Reports one address may send per hour (default 20). |

## Read reports

Open `https://<your host>/admin` and enter the token. Each report shows its
category, version, time, the person's words and contact (if given), and a
button for its diagnostics zip (logs, errors, versions; never sign-in data).

## Switch reporting on in the app

Set the address in `Backend/dannify/report.py`:

```python
REPORT_ENDPOINT = 'https://<your host>/reports'
```

and release a new version. Until then the app shows Report a problem as
"Coming soon". Reports that could not be sent (offline) are kept by the app
and sent later.
