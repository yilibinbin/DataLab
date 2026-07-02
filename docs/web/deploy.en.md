# Deployment & Configuration

This page contains technical details for running DataLab Web, including Python/Flask setup and environment variables.

## Stack

- **Backend**: Flask (Python web framework)
- **Numerics**: mpmath (multi-precision floating point)
- **Frontend**: plain HTML + CSS + JavaScript
- **LaTeX engines**: pdflatex / xelatex

## Run Locally

### Requirements
- Python 3.8+
- Python dependencies (see `web_requirements.txt`)

### Steps

```bash
# 1. Enter the project directory
cd /path/to/data_extrapolation_source

# 2. Install dependencies
pip install -r web_requirements.txt

# 3. Start the server
python app_web/server.py
```

### Open in Browser

Visit: `http://127.0.0.1:8000`

### Environment Variables (optional)

```bash
# Bind address (default 127.0.0.1)
export DATALAB_HOST=0.0.0.0

# Port (default 8000)
export DATALAB_PORT=5000

# Enable debug (development only!)
export DATALAB_DEBUG=1
```

## Production Deployment

### Option 1: Gunicorn + Nginx

> Note: **Gunicorn is POSIX-only** (Linux/macOS). It will not run on native Windows because it depends on `fcntl`.

```bash
# 1. Install gunicorn
pip install gunicorn

# 2. Start gunicorn (4 workers)
gunicorn -w 4 -b 127.0.0.1:8000 app_web.server:app

# 3. Configure nginx reverse proxy
# /etc/nginx/sites-available/datalab
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# 4. Restart nginx
sudo systemctl restart nginx
```

### Option 2: systemd Service

Create `/etc/systemd/system/datalab-web.service`:

```ini
[Unit]
Description=DataLab Web Application
After=network.target

[Service]
Type=notify
User=www-data
WorkingDirectory=/path/to/data_extrapolation_source
Environment="DATALAB_WEB_SECRET=your-secret-key-here"
Environment="DATALAB_HOST=127.0.0.1"
Environment="DATALAB_PORT=8000"
ExecStart=/usr/bin/gunicorn -w 4 -b 127.0.0.1:8000 app_web.server:app
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable datalab-web
sudo systemctl start datalab-web
```

### Windows (native): Waitress

Gunicorn does not support Windows. Use Waitress instead:

```powershell
pip install waitress
waitress-serve --listen=192.168.85.1:8000 --threads=8 app_web.server:app
```

If you need multi-process workers on Windows, consider running the service in **WSL2/Docker** and using Gunicorn there.

## Built-in Docs (`/docs`)

The web app provides built-in docs via `/docs` and `/docs/<page>`:

- Documentation files are loaded **only** from `docs/web/` with a strict whitelist (prevents path traversal)
- File naming: `docs/web/<page>.<lang>.md` where `lang ∈ {zh,en}`
- Language selection priority:
  1) Query parameter `?lang=zh` or `?lang=en`
  2) Cookie `datalab_lang`
  3) Default `zh`
- If an English page is missing, an English placeholder page is shown (no fallback to Chinese)

## Configuration

### Required (production)

**`DATALAB_WEB_SECRET`** — Flask secret key
- Used for session signing and CSRF tokens
- Must be random and kept secret (at least 32 characters)
- Default `datalab-web-dev` is for development only

Generate a key:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### Optional

| Variable | Default | Description |
|---------|---------|-------------|
| `DATALAB_HOST` | `127.0.0.1` | Bind address (`0.0.0.0` = all interfaces) |
| `DATALAB_PORT` | `8000` | Port |
| `PORT` | `8000` | Fallback port (cloud platforms) |
| `DATALAB_DEBUG` | `0` | Debug mode (`1` enables, production must be `0`) |
| `DATALAB_TRUST_PROXY_HEADERS` | `0` | Trust `X-Forwarded-*` headers via werkzeug `ProxyFix` (`1`/`true`/`yes`/`on` enables). Set **only** when behind a trusted reverse proxy — otherwise clients can spoof their IP and bypass the SSE rate limiter |
| `DATALAB_SSE_DISABLE_RATE_LIMIT` | unset | If set (any value), turns **off** the per-IP SSE rate limiter for the process. Development only — production deployments must not set this |
| `DATALAB_LATEX_TIMEOUT` | `30` | Wall-clock timeout (seconds) for each LaTeX compilation subprocess |
| `DATALAB_LATEX_MAX_CPU` | `60` | CPU-time limit (seconds) per LaTeX subprocess (POSIX `RLIMIT_CPU`) |
| `DATALAB_LATEX_MAX_MEM` | `512` | Address-space limit (MB) per LaTeX subprocess (POSIX `RLIMIT_AS`) |
| `DATALAB_LATEX_MAX_FILE` | `50` | Max output file size (MB) per LaTeX subprocess (POSIX `RLIMIT_FSIZE`) |
| `DATALAB_LATEX_MAX_PROC` | `2048` | Max processes per user for the LaTeX subprocess (POSIX `RLIMIT_NPROC`); lower values can break XeLaTeX/LuaLaTeX on busy machines |

## Security Notes

- Do not hard-code secrets into source code
- Use HTTPS in production
- Limit upload sizes (built-in validation exists)
- Keep LaTeX compilation sandboxed and time-limited

## Logs & Debugging

- Run with `DATALAB_DEBUG=1` in development only
- For systemd deployments, use `journalctl -u datalab-web -f`
