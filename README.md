# Data Extrapolation GUI

GUI tool for extrapolation/error-propagation workflows with LaTeX export and inline PDF preview. The same codebase targets macOS and Windows; each platform has a helper script to produce fully self-contained builds (Python and third-party libraries are bundled).

## Requirements

- Python 3.10+
- Desktop GUI: `pip install -r gui_requirements.txt` (PySide6 + scientific stack)
- Web app: `pip install -r web_requirements.txt` (Flask)
- Tests (optional): `pip install -r requirements-test.txt` (pytest-qt / pytest-cov)
- A TeX distribution (MiKTeX, TeX Live, etc.) providing `pdflatex` or `xelatex`. The GUI can auto-detect common locations or let you browse to a custom executable.

## Web 版本（DataLab Web） - 高精度外推与误差分析工具

基于同一套科学计算模块构建的 Flask Web 应用，支持多语言、交互式帮助和完整文档系统。

### ✨ 主要特性

#### 核心功能
- **序列外推**：幂律、Richardson、Shanks、Levin u-transform、自定义公式
- **误差传递**：对 `1.23(4)[-2]` 形式数据执行公式计算，自动传播不确定度
- **曲线拟合**：自动模型选择、多项式、Padé、自定义模型
- **统计分析**：加权平均、样本方差、统计平均

#### UI/UX 特性（v2.0 新增）
- 🌐 **多语言支持**：中文/English 一键切换
- ❓ **交互式帮助**："?" 按钮弹窗说明
- 📚 **文档**：Web 内嵌文档页面
- 🌓 **深色主题**：护眼深色界面

### 快速启动

```bash
# 方法 1: 使用虚拟环境（推荐）
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r web_requirements.txt
python app_web/server.py

# 方法 2: 直接安装
pip install -r web_requirements.txt
python app_web/server.py
```

访问：http://127.0.0.1:8000

### 📚 详细文档

- [快速启动指南](QUICK_START.md) - 完整安装和使用说明
- [DataLab Web 指南](docs/DATALAB_WEB_GUIDE.md) - 使用说明与技术细节（中文）
- [测试矩阵](docs/TEST_MATRIX.md) - 回归覆盖与验收清单
- **在线文档**（启动服务器后访问）：
  - Web 内嵌文档：http://127.0.0.1:8000/docs

### 🌐 多语言使用

点击右上角语言下拉框切换中文/English，设置自动保存到浏览器。

### ❓ 交互式帮助

- 点击公式输入框旁的 "?" 查看可用函数列表
- 点击外推方法旁的 "?" 查看方法说明和参数解释
- 帮助内容支持中英文切换

### 🔧 配置

环境变量：
- `DATALAB_WEB_SECRET`：Flask 密钥（生产环境必须设置）
- `DATALAB_HOST`：监听地址（默认 127.0.0.1）
- `DATALAB_PORT`：监听端口（默认 8000）
- `DATALAB_DEBUG`：调试模式（生产环境必须为 0）

生产环境部署详见：[docs/web/deploy.md](docs/web/deploy.md)（或启动后访问 `/docs/deploy`）

> Windows 原生环境不能使用 Gunicorn（会报 `No module named 'fcntl'`）；请按 `docs/web/deploy.md` 使用 Waitress，或在 WSL2/Docker 内用 Gunicorn。

## Run from Source

```bash
# Desktop GUI
python3 data_extrapolation_gui.py

# Web
python3 app_web/server.py
```

The “选项” panel lets you choose between `pdflatex` and `xelatex`. If the executable is not on `PATH`, click “选择引擎路径...” to browse to it once; the path is cached for subsequent runs.

## Development & Testing

```bash
# Install test deps (optional)
pip install -r requirements-test.txt

# Headless GUI tests on CI / servers
QT_QPA_PLATFORM=offscreen pytest -q
```

Notes:
- `data_extrapolation_latex_latest.py` is a backwards-compatible shim; the implementation lives in `datalab_latex/`.
- Web routes are organized as Blueprints under `app_web/blueprints/`, and heavy computations live in the `app_web/logic/` package.

## Advanced Extrapolation Methods

- Select the extrapolation algorithm via the new drop-down (next to the pdflatex selector style). Available choices: quadratic (MATLAB formula), power-law, Richardson, Shanks, and Levin *u*-transform.
- The precision entry controls the mpmath working digits for every method that relies on high-precision arithmetic (power-law + sequence accelerators). Leave it at ≥50 for stable convergence; raise it for difficult datasets.
- When power-law is active you can still edit the three basis radii (`x1/x2/x3`) and optionally pin the exponent `p`. For the other accelerators only the precision entry is needed.
- The uncertainty column selector continues to specify which of the loaded columns (A/B/C or their custom headers) is subtracted from the extrapolated limit to estimate σ.
- All implementations live under `extrapolation_methods/` so the GUI, CLI, and packaged builds share one code path.
- Internally every extrapolation path now uses `mpmath` mpf numbers (no `decimal.Decimal`), so a single precision knob governs the CLI, GUI, power-law solver, and the Richardson/Shanks/Levin accelerators.

## Package on macOS

```bash
cd /path/to/DataLab
chmod +x build_mac_data_gui.sh
./build_mac_data_gui.sh
```

Highlights:

- The script creates a temporary virtual environment, installs all dependencies, and uses PyInstaller to emit `dist/DataExtrapolationGUI.app`.
- It automatically selects a Python interpreter whose deployment target is compatible with the host macOS; if necessary it bootstraps a portable CPython build.
- After PyInstaller finishes, the script strips extended attributes and applies an ad-hoc signature so the `.app` can be launched via Finder (you may still need to clear the quarantine bit the first time: `xattr -dr com.apple.quarantine dist/DataExtrapolationGUI.app`).

## Package on Windows

```powershell
cd C:\path\to\DataLab
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\build_windows_data_gui.ps1
```

This produces `dist\DataExtrapolationWin_Performance\` (onedir) and `dist\DataExtrapolationWin_OneFile.exe` (single EXE). The PowerShell script:

- Creates a venv, installs requirements plus PyInstaller.
- Converts `data_draw_app.png` into a multi-size `.ico` at build time so Explorer/taskbar show the custom artwork, and bundles both PNG/ICO so the PySide6 window can use the same icon at runtime.
- No system-wide dependencies are required on the target machine; everything ships inside the `dist` output.

## Notes

- The cross-platform GUI renders PDF output inside a dedicated tab after each successful LaTeX compile. If an inline preview cannot be generated (missing Poppler/Ghostscript/Pillow), the app falls back to launching the default PDF viewer.
- All runtime selections (LaTeX engine paths, last opened files, etc.) are logged in the “日志” tab for easier troubleshooting.
