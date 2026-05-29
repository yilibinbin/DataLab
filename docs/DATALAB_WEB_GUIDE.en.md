# DataLab Web User & Technical Guide

中文版本：DATALAB_WEB_GUIDE.md

This document has two parts:
- **Part I: User guide** - for end users, explaining how to use DataLab Web features
- **Part II: Technical & deployment guide** - for developers and operators, describing architecture, deployment, and configuration

---

## Part I: User Guide

### 1. Overview

DataLab Web is a browser-based, high-precision numerical tool that provides four major modules:

#### 1.1 Extrapolation
- **Purpose**: extrapolate numerical sequences to estimate a limit or trend
- **Supported methods**:
  - Power-law extrapolation (3-point)
  - Richardson sequence acceleration
  - Shanks transform / Wynn ε algorithm
  - Levin u-transform
  - Custom-formula extrapolation
  - Default 3-point formula

#### 1.2 Error Propagation
- **Purpose**: propagate uncertainties through formulas
- **Features**:
  - Numerical partial derivatives
  - Automatic uncertainty combination
  - Joint propagation of constants and data

#### 1.3 Fitting
- **Purpose**: fit curves to data and obtain best-fit parameters
- **Supported models**:
  - Polynomial fitting
  - Inverse-power series fitting
  - Padé approximation
  - Power-limit template
  - Custom models

#### 1.4 Statistics
- **Purpose**: (weighted or unweighted) statistical averaging of uncertain data
- **Supported modes**:
  - Simple mean
  - Sample-variance estimation
  - Weighted variance

---

### 2. Data Input

#### 2.1 Paste text
1. Paste data directly into the input box
2. The first row is the header (column names); following rows are data
3. Columns are separated by spaces or tabs

**Example**:
```
A B C
-0.750000   -0.702321   -0.680145
-0.500000   -0.476901   -0.461822
-0.250000   -0.235440   -0.228512
```

#### 2.2 Upload a file
1. Check “Use file input”
2. Click “Upload UTF-8 text file”
3. Choose a `.txt`, `.dat`, or `.csv` file
4. File format is the same as pasted text (header row + data rows)

#### 2.3 Uncertainty formats

DataLab Web supports two uncertainty representations:

**Format 1: Parenthesis notation** - `value(unc_digits)[10_exponent]`
```
1.2345(67)       # means 1.2345 ± 0.0067
1.2345(67)[-2]   # means 1.2345 ± 0.0067 × 10^-2
```

**Format 2: Separate columns** - value and uncertainty in two columns
```
value     uncertainty
1.2345    0.0067
2.3456    0.0089
```

---

### 3. Module Usage

### 3.1 Extrapolation

#### Steps
1. **Input data**: paste or upload multi-column data
2. **Choose an extrapolation method**:
   - **Power-law**: for sequences that match `f(x) = A*x^(-p) + C`
   - **Richardson**: for sequences with asymptotic expansions
   - **Shanks/Wynn**: general-purpose acceleration
   - **Levin u-transform**: for oscillatory or slowly convergent sequences
   - **Custom formula**: define your own extrapolation rule via an expression
3. **Set parameters**:
   - **Reference column**: used to compute the uncertainty (column name or index)
   - **High precision mp.dps**: numerical precision (blank uses default 16)
   - **Result uncertainty digits**: controls display precision of uncertainties
4. **Generate output**:
   - Click “Run extrapolation and generate LaTeX”
   - View the result table, LaTeX code, optional plots, and PDF

#### Formula syntax (Custom extrapolation)
- Use `A, B, C` or column names to refer to columns
- Use `x1, x2, x3, ...` as column aliases
- Supported functions: `Sin[x]`, `Cos[x]`, `Log[x]`, `Exp[x]`, `Sqrt[x]`, `Abs[x]`
- Example: `(C - B)^2/(B - A) + C`

---

### 3.2 Error Propagation

#### Steps
1. **Input data**: use parenthesis notation to enter uncertain data
   ```
   E1 E2 E3
   1.0000(5)   0.8000(4)   0.7000(2)
   1.2000(5)   0.9500(4)   0.8200(3)
   ```
2. **Enter a formula**: in the “Error propagation formula” box
   - Use column names or `x1, x2, x3` aliases
   - Functions use Mathematica-style names: `Sin[x1]`, `Log[ALPHA]`
3. **Optional: Add constants**
   - Check “Enable constants”
   - Enter a constant list (one per line):
     ```
     ALPHA 7.2973525693(11)[-3]
     BETA 1.0000(5)
     ```
4. **Generate output**
   - Click “Run error propagation and generate LaTeX”
   - View propagated results and the uncertainty contribution breakdown plot

#### Formula examples
```
x1*ALPHA + x2/x3               # simple arithmetic
Sin[x1]^2 + Cos[x1]^2          # trig functions
Exp[-x1*ALPHA] * x2            # exponential and multiplication
Log[x1/x2] + Sqrt[x3]          # log and sqrt
```

---

### 3.3 Fitting

#### Steps
1. **Input data**: upload or paste `x y` data
   - Uncertainties may be included as `x y(σ)` or `x y σ`
   ```
   x y
   1.0  2.1(5)
   2.0  4.2(5)
   3.0  6.0(5)
   ```
2. **Choose a fitting mode**
   - **Polynomial fit**: specify degree
   - **Inverse-power series**: specify power range
   - **Padé fit**: specify numerator and denominator order
   - **Power-limit fit**: use the `A*x**(-p)+C` template
   - **Custom model**: enter a custom expression
3. **Set options**
   - **Weighted fitting**: use uncertainties as weights
   - **Log coordinates**: choose `log-x`, `log-y`, or `log-log`
4. **Inspect results**
   - Fit parameters and uncertainties
   - Fit quality metrics (χ², AIC, BIC, R², RMSE)
   - Fitted curve and residual plots

---

### 3.4 Statistics

#### Steps
1. **Input data**: enter a single column (may include uncertainties)
   ```
   A
   1152842742.723(12)
   1152842742.740(18)
   1152842742.727(14)
   ```
2. **Choose a statistics mode**
   - **Simple mean**: arithmetic mean
   - **Sample variance estimate**: check “Use sample standard deviation”
   - **Weighted variance**: check “Use weighted variance”
3. **Inspect results**
   - Mean ± standard error
   - Min/max/standard deviation
   - Count of valid data points

---

### 4. Output Notes

#### 4.1 Result tables
- **Extrapolated/result value**: computed output
- **Uncertainty**: error or standard deviation
- **LaTeX format**: formatted output in parenthesis notation

#### 4.2 Formatting controls
- **Scientific notation**: toggle via checkbox
- **Digits**: adjust the number of significant digits shown

#### 4.3 Export options
- **Download CSV**: export table data
- **LaTeX code**: copy the LaTeX text into papers/reports
- **Download PDF**: if PDF compilation is enabled, download a full PDF

---

### 5. FAQ

#### Q1: Why does my formula fail?
A: Check that:
- Functions use Mathematica-style capitalization: `Sin[x]` instead of `sin(x)`
- Column names / constants are spelled correctly
- Only supported functions are used (Sin, Cos, Log, Exp, Sqrt, Abs)

#### Q2: What are the column reference rules?
A: Three ways are supported:
- **Column names**: use headers directly
- **x1, x2, x3**: positional aliases (x1 = first column, x2 = second, ...)
- **A, B, C**: special aliases in extrapolation mode

#### Q3: What are the limitations of log-coordinate fitting?
A: With log coordinates:
- `log-x` requires all x > 0
- `log-y` requires all y > 0
- `log-log` requires all x, y > 0

#### Q4: How should I interpret the uncertainty contribution plot?
A: It shows the percentage contribution of each input variable to the total uncertainty, helping identify the dominant sources.

#### Q5: When do I need high precision (`mp.dps`)?
A: Consider a higher `mp.dps` when:
- Using power-law extrapolation (default 80 digits)
- Using Richardson/Shanks acceleration (default 80 digits)
- Your data requires very high precision

---

## Part II: Technical & Deployment Guide

### 1. System Architecture

#### 1.1 Tech stack
- **Backend framework**: Flask (Python)
- **Numerics**: mpmath (arbitrary-precision floating-point)
- **Shared scientific core**: shared computation module based on `data_extrapolation_latex_latest.py`
- **Frontend**: plain HTML + CSS + JavaScript (no external frontend framework)
- **LaTeX engines**: pdflatex / xelatex (for PDF generation)

#### 1.2 Architecture highlights
- **Pure Python**: no Node.js or extra runtimes required
- **Modular design**: frontend/backend separation; core computations can be reused independently
- **Shared codebase**: Web and Desktop (Qt GUI) reuse the same scientific core
- **Security hardening**: built-in CSRF protection, input validation, and sandboxed LaTeX compilation

---

### 2. Run Locally

#### 2.1 Requirements
- Python 3.8+
- Dependencies (see `web_requirements.txt` or `gui_requirements.txt`)

#### 2.2 Installation

```bash
# 1. Clone or download the project
cd /path/to/data_extrapolation_source

# 2. Install dependencies
pip install -r web_requirements.txt

# 3. Run the server
python app_web/server.py
```

#### 2.3 Access
Open: `http://127.0.0.1:8000`

#### 2.4 Environment variables (optional)
```bash
# Bind address (default 127.0.0.1)
export DATALAB_HOST=0.0.0.0

# Port (default 8000)
export DATALAB_PORT=5000

# Debug mode (development only!)
export DATALAB_DEBUG=1
```

---

### 3. Server Deployment

#### 3.1 Production deployment options

**Recommended option 1: Gunicorn + Nginx**

```bash
# 1. Install Gunicorn
pip install gunicorn

# 2. Start Gunicorn (4 workers)
gunicorn -w 4 -b 127.0.0.1:8000 app_web.server:app

# 3. Configure Nginx reverse proxy
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

# 4. Restart Nginx
sudo systemctl restart nginx
```

**Recommended option 2: systemd service**

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

Start the service:
```bash
sudo systemctl enable datalab-web
sudo systemctl start datalab-web
```

---

### 4. Configuration & Environment Variables

#### 4.1 Required (production)

**`DATALAB_WEB_SECRET`** - Flask secret key
- **Purpose**: session encryption and CSRF token generation
- **Security**: must be random and private (≥ 32 chars recommended)
- **Default**: `datalab-web-dev` (development only; must be changed in production)

Secret generation examples:
```bash
# Option 1: Python
python -c "import secrets; print(secrets.token_hex(32))"

# Option 2: OpenSSL
openssl rand -hex 32

# Set the env var
export DATALAB_WEB_SECRET="your-generated-secret-key"
```

#### 4.2 Optional configuration

| Env var | Default | Description |
|---------|---------|-------------|
| `DATALAB_HOST` | `127.0.0.1` | Bind address (`0.0.0.0` = all interfaces) |
| `DATALAB_PORT` | `8000` | Port |
| `PORT` | `8000` | Backup port var (cloud platforms) |
| `DATALAB_DEBUG` | `0` | Debug mode (`1` on; production must be `0`) |

---

### 5. Security Recommendations

#### 5.1 Secret management
- ✅ **DO**: store `DATALAB_WEB_SECRET` in env vars or a secret manager
- ✅ **DO**: rotate secrets regularly
- ❌ **DON'T**: hardcode secrets in source code
- ❌ **DON'T**: commit secrets to version control

#### 5.2 HTTPS
Production must use HTTPS:
```bash
# Use a free Let's Encrypt certificate
sudo certbot --nginx -d your-domain.com
```

#### 5.3 Reverse-proxy security headers
Add to Nginx config:
```nginx
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-XSS-Protection "1; mode=block" always;
add_header Referrer-Policy "no-referrer-when-downgrade" always;
```

#### 5.4 Upload limits
The app enforces an input size limit (default 1MB). To adjust:
- Update `MAX_TEXT_SIZE` in `app_web/security.py`
- Also adjust Nginx `client_max_body_size`

#### 5.5 LaTeX security
- LaTeX compilation runs sandboxed (`-no-shell-escape`)
- Compilation timeout is enforced (30 seconds)
- Only whitelisted engines are allowed (`pdflatex`, `xelatex`, `lualatex`)

---

### 6. Logging & Debugging

#### 6.1 Application logs
Flask logs to stdout by default. With systemd:
```bash
# Follow logs
sudo journalctl -u datalab-web -f

# Last 100 lines
sudo journalctl -u datalab-web -n 100
```

#### 6.2 Debug mode
**Development only!**
```bash
export DATALAB_DEBUG=1
python app_web/server.py
```

Debug mode:
- shows detailed error pages
- auto-reloads on code changes
- prints verbose logs

**Warning**: Never enable debug in production; it may leak sensitive information.

---

### 7. Build & Upgrade

#### 7.1 Upgrade dependencies
```bash
# Upgrade Python packages
pip install -r web_requirements.txt --upgrade

# Verify versions
pip list | grep Flask
pip list | grep mpmath
```

#### 7.2 Database migrations
Current versions do not use a database; all computations are stateless.

#### 7.3 Hot reload
Smooth reload with Gunicorn:
```bash
# Reload via HUP
kill -HUP $(cat /var/run/gunicorn.pid)

# Or via systemd
sudo systemctl reload datalab-web
```

---

### 8. Performance Optimization

#### 8.1 Worker count
Recommended Gunicorn worker count:
- **CPU-bound** (this app is CPU-bound): `2 × CPU cores + 1`
- Example: 4-core CPU → 9 workers

```bash
gunicorn -w 9 -b 127.0.0.1:8000 app_web.server:app
```

#### 8.2 Caching
Current versions do not cache results. For acceleration:
- Use Redis to cache repeated computations
- Implement a task queue (Celery)

#### 8.3 Resource limits
Use systemd resource constraints:
```ini
[Service]
MemoryMax=2G
CPUQuota=200%
```

---

### 9. Troubleshooting

#### 9.1 Common issues

**Issue 1: LaTeX compilation fails**
- **Cause**: LaTeX not installed
- **Fix**:
  ```bash
  # Ubuntu/Debian
  sudo apt-get install texlive texlive-latex-extra

  # macOS
  brew install --cask mactex
  ```

**Issue 2: Port is in use**
- **Symptom**: `Address already in use`
- **Fix**:
  ```bash
  # Find process
  lsof -i :8000

  # Kill it or change port
  export DATALAB_PORT=8001
  ```

**Issue 3: Permission errors**
- **Symptom**: `Permission denied`
- **Fix**: ensure the runtime user can access the working directory and log directory

#### 9.2 Performance issues
- **High-precision runs are slow**: expected; higher mp.dps is slower
- **Slow under concurrency**: increase workers or use async workers (`gunicorn -k gevent`)

---

### 10. API Endpoints (internal reference)

DataLab Web provides the following endpoints for the frontend:

| Endpoint | Method | Purpose |
|------|------|------|
| `/` | GET/POST | Extrapolation page |
| `/error` | GET/POST | Error propagation page |
| `/fit` | GET/POST | Fitting page |
| `/stats` | GET/POST | Statistics page |
| `/api/ui-specs` | GET | UI dynamic configuration |
| `/api/function-help` | GET | Function help text |
| `/api/method-help/<method>` | GET | Method help |

---

### 11. Developer Notes

#### 11.1 Project structure
```
data_extrapolation_source/
├── app_web/                    # Web application
│   ├── server.py              # Flask entry
│   ├── security.py            # Security (CSRF, input validation)
│   ├── latex_security.py      # Safe LaTeX compilation
│   ├── templates/             # Jinja2 templates
│   │   ├── base.html         # Base template
│   │   ├── index.html        # Extrapolation
│   │   ├── error.html        # Error propagation
│   │   ├── fit.html          # Fitting
│   │   └── stats.html        # Statistics
│   └── static/                # Static assets
│       ├── style.css         # Styles
│       └── ui_specs.js       # Frontend logic
├── data_extrapolation_latex_latest.py  # Shared computation core
├── extrapolation_methods/     # Extrapolation algorithms
├── fitting/                   # Fitting module
├── statistics_utils.py        # Statistics utilities
└── docs/                      # Docs
    └── DATALAB_WEB_GUIDE.md  # This document
```

#### 11.2 Adding new features
1. Modify the corresponding route handler (`app_web/server.py`)
2. Update templates (`app_web/templates/`)
3. If frontend interaction is needed, update `ui_specs.js`
4. Add test cases

#### 11.3 Testing
```bash
# Run security tests
python app_web/test_security.py

# Manually test CSRF protection:
# (start the server, open any page, and check the form includes csrf_token)
```

---

### 12. License & Contributions

This is a research tool. Please follow the relevant terms of use. For issues or suggestions, contact the maintainers.

---

**Document version**: v1.0  
**Last updated**: 2025-12-13  
**Maintainer**: DataLab Team
