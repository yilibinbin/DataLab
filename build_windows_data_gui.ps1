[CmdletBinding()]
param(
    [string]$PythonPath = "",
    [switch]$SkipOneFile,
    [string]$IconPath = "",
    [switch]$UseExistingPython,
    # Opt-in: bundle TinyTeX (~200 MB) into the installer so users
    # without a local TeX Live install can compile PDFs offline. The
    # runtime discovery layer (shared.latex_engine) looks under
    # <app>\resources\tinytex\bin\<arch>; the installer step below
    # puts it exactly there.
    [switch]$BundleTinyTeX,
    [switch]$BuildInnoInstaller,
    [string]$InnoSetupPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-WithArgs {
    param(
        [string[]]$BaseCommand,
        [string[]]$ExtraArgs = @()
    )
    $full = $BaseCommand + $ExtraArgs
    if ($full.Length -eq 0) {
        throw "No command specified."
    }
    # Bracket the call with a relaxed ErrorActionPreference so a native
    # tool that writes to stderr (PyInstaller emits ``INFO:`` lines on
    # stderr by design) is not treated as a PowerShell-level error
    # under ``$ErrorActionPreference = "Stop"``. We instead inspect
    # ``$LASTEXITCODE`` ourselves and throw on a non-zero exit so a
    # genuine compile failure still aborts the script.
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        if ($full.Length -eq 1) {
            & $full[0]
        } else {
            & $full[0] @($full[1..($full.Length - 1)])
        }
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed (exit $LASTEXITCODE): $($full -join ' ')"
    }
}

function Resolve-Python {
    param([string[][]]$Candidates)
    $probe = @'
import sys
from pathlib import Path

if sys.version_info < (3, 10):
    raise SystemExit('too_old_python')

print(Path(sys.executable).resolve())
'@
    foreach ($candidate in $Candidates) {
        if (-not $candidate) {
            continue
        }
        try {
            $output = Invoke-WithArgs $candidate @("-c", $probe)
            if ($LASTEXITCODE -eq 0 -and $null -ne $output) {
                $text = (@($output) -join [Environment]::NewLine)
                if ($text) {
                    $segments = $text -split "`r?`n"
                    $path = $segments[-1].Trim()
                    if ($path) {
                        return $path
                    }
                }
            }
        } catch {
            continue
        }
    }
    throw "Unable to locate a Python 3.10+ interpreter. Provide -PythonPath to override."
}

function New-BuildDirectory {
    param([string]$Path)
    if (Test-Path $Path) {
        Remove-Item -Path $Path -Recurse -Force
    }
    New-Item -ItemType Directory -Path $Path | Out-Null
}

function Get-ProjectVersion {
    param([string]$PyprojectPath)
    if (-not (Test-Path $PyprojectPath)) {
        throw "pyproject.toml not found: $PyprojectPath"
    }

    foreach ($line in Get-Content -Path $PyprojectPath -Encoding UTF8) {
        if ($line -match '^\s*version\s*=\s*"([^"]+)"\s*$') {
            return $Matches[1]
        }
    }
    throw "Unable to parse project version from pyproject.toml."
}

function Resolve-InnoSetupCompiler {
    param([string]$PathOverride)

    $candidates = @()
    if ($PathOverride) {
        if (Test-Path $PathOverride -PathType Container) {
            $candidates += (Join-Path $PathOverride "ISCC.exe")
        } else {
            $candidates += $PathOverride
        }
    }

    $programFilesX86 = [Environment]::GetFolderPath("ProgramFilesX86")
    if ($programFilesX86) {
        $candidates += (Join-Path $programFilesX86 "Inno Setup 6\ISCC.exe")
    }

    $programFiles = [Environment]::GetFolderPath("ProgramFiles")
    if ($programFiles) {
        $candidates += (Join-Path $programFiles "Inno Setup 6\ISCC.exe")
    }

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate -PathType Leaf)) {
            return (Resolve-Path $candidate).Path
        }
    }

    $pathCommand = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
    if ($pathCommand) {
        return $pathCommand.Source
    }

    throw "Unable to locate ISCC.exe. Install Inno Setup 6, add ISCC.exe to PATH, or pass -InnoSetupPath."
}

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$buildRoot = Join-Path $projectRoot "build\windows_gui_build"
$venvPath = Join-Path $buildRoot "venv"
$entryFile = Join-Path $projectRoot "data_extrapolation_gui.py"
$distDir = Join-Path $projectRoot "dist"
$iconTargetIco = Join-Path $buildRoot "DataLab.ico"
$iconTargetPng = Join-Path $buildRoot "DataLab.png"

$iconSource = $null
if ($PSBoundParameters.ContainsKey("IconPath") -and $IconPath) {
    if (-not (Test-Path $IconPath)) {
        throw "Icon path not found: $IconPath"
    }
    $iconSource = (Resolve-Path $IconPath).Path
} else {
    $defaultIcon = Join-Path $projectRoot "DataLab.png"
    if (Test-Path $defaultIcon) {
        $iconSource = (Resolve-Path $defaultIcon).Path
    }
}

Write-Host "[1/6] Preparing build workspace..."
New-BuildDirectory -Path $buildRoot
New-BuildDirectory -Path $distDir

$pythonCandidates = @()
if ($PythonPath) {
    $pythonCandidates += ,@($PythonPath)
}
$pythonCandidates += ,@("py", "-3.11")
$pythonCandidates += ,@("py", "-3.10")
$pythonCandidates += ,@("py", "-3")
$pythonCandidates += ,@("python3")
$pythonCandidates += ,@("python")

$pythonExe = Resolve-Python -Candidates $pythonCandidates
Write-Host ("[info] Selected Python interpreter: {0}" -f $pythonExe)

$usingExisting = $UseExistingPython.IsPresent
if ($usingExisting) {
    Write-Host "[2/6] Reusing existing Python environment."
    $venvPython = $pythonExe
} else {
    Write-Host "[2/6] Creating isolated virtual environment..."
    Invoke-WithArgs @($pythonExe) @("-m", "venv", $venvPath)
    $venvPython = Join-Path $venvPath "Scripts\python.exe"
    if (-not (Test-Path $venvPython)) {
        throw "Virtual environment was not created correctly."
    }
    Write-Host "[3/6] Installing Python dependencies..."
    Invoke-WithArgs @($venvPython) @("-m", "pip", "install", "--upgrade", "pip", "wheel", "setuptools")
    Invoke-WithArgs @($venvPython) @("-m", "pip", "install", "-r", (Join-Path $projectRoot "gui_requirements.txt"))
    Invoke-WithArgs @($venvPython) @("-m", "pip", "install", "pyinstaller")
}

if ($usingExisting) {
    Write-Host "[3/6] Skipping dependency installation (using existing environment)."
    Write-Host "       Ensure PySide6, Pillow, mpmath, and PyInstaller are already installed in this interpreter."
}

Write-Host "[4/6] Preparing icon..."
$iconArgs = @()
$dataArgs = @()
if ($iconSource) {
    $iconScript = @"
import sys
from pathlib import Path
from PIL import Image

src = Path(sys.argv[1])
dst_png = Path(sys.argv[2])
dst_ico = Path(sys.argv[3])
dst_png.parent.mkdir(parents=True, exist_ok=True)

with Image.open(src) as im:
    im = im.convert("RGBA")
    im.save(dst_png, format="PNG")
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    im.save(dst_ico, format="ICO", sizes=sizes)
"@
    $iconScriptPath = Join-Path $buildRoot "make_icon.py"
    Set-Content -Path $iconScriptPath -Value $iconScript -Encoding UTF8
    Invoke-WithArgs @($venvPython) @($iconScriptPath, $iconSource, $iconTargetPng, $iconTargetIco)
    Remove-Item -Path $iconScriptPath -Force

    if (Test-Path $iconTargetIco) {
        $iconArgs = @("--icon", $iconTargetIco)
        $dataArgs += @("--add-data", ("{0};." -f $iconTargetIco))
    } else {
        Write-Warning "Icon conversion failed; continuing without a custom icon."
    }

    if (Test-Path $iconTargetPng) {
        $dataArgs += @("--add-data", ("{0};." -f $iconTargetPng))
    } else {
        Write-Warning "PNG icon asset missing; GUI will fall back to default."
    }
} else {
    Write-Warning "No icon source provided; builds will use the default PyInstaller icon."
}

# Bundle desktop docs (docs\\desktop) into the packaged app.
$pyprojectFile = Join-Path $projectRoot "pyproject.toml"
if (Test-Path $pyprojectFile) {
    $pyprojectAbs = (Resolve-Path $pyprojectFile).Path
    Write-Host ("[info] Including project metadata: {0}" -f $pyprojectAbs)
    $dataArgs += @("--add-data", ("{0};." -f $pyprojectAbs))
} else {
    Write-Warning ("pyproject.toml not found: {0}" -f $pyprojectFile)
}

$desktopDocsDir = Join-Path $projectRoot "docs\\desktop"
if (Test-Path $desktopDocsDir) {
    $desktopDocsAbs = (Resolve-Path $desktopDocsDir).Path
    Write-Host ("[info] Including desktop docs: {0}" -f $desktopDocsAbs)
    $dataArgs += @("--add-data", ("{0};docs\\desktop" -f $desktopDocsAbs))
} else {
    Write-Warning ("Desktop docs directory not found: {0}" -f $desktopDocsDir)
}

# Bundle shared help specs used by "?" help buttons.
$helpSpecsFile = Join-Path $projectRoot "shared\\help_specs.json"
if (Test-Path $helpSpecsFile) {
    $helpSpecsAbs = (Resolve-Path $helpSpecsFile).Path
    Write-Host ("[info] Including help specs: {0}" -f $helpSpecsAbs)
    $dataArgs += @("--add-data", ("{0};shared" -f $helpSpecsAbs))
} else {
    Write-Warning ("Help specs file not found: {0}" -f $helpSpecsFile)
}

# Optional: bundle TinyTeX (~200 MB) so users without a local TeX Live
# install can compile PDFs offline. Opt-in via the -BundleTinyTeX flag
# because the bundle size impact is large. The runtime discovery layer
# (shared.latex_engine) looks under <app>\resources\tinytex\bin\<arch>;
# the installer + --add-data pair below put it exactly there.
if ($BundleTinyTeX) {
    Write-Host "[info] Bundling TinyTeX (-BundleTinyTeX)..."
    $tinytexDir = Join-Path $projectRoot "resources\\tinytex"
    $bashExe = (Get-Command bash -ErrorAction SilentlyContinue).Source
    if ($bashExe) {
        & $bashExe (Join-Path $projectRoot "tools/install_tinytex.sh")
        if (Test-Path $tinytexDir) {
            $tinytexAbs = (Resolve-Path $tinytexDir).Path
            Write-Host ("[info] Including TinyTeX bundle: {0}" -f $tinytexAbs)
            $dataArgs += @("--add-data", ("{0};resources\\tinytex" -f $tinytexAbs))
        } else {
            Write-Warning ("TinyTeX install ran but {0} missing." -f $tinytexDir)
        }
    } else {
        Write-Warning "bash.exe not found; cannot run tools/install_tinytex.sh on Windows. Install Git Bash / WSL and re-run."
    }
}

$pyinstallerBase = @($venvPython, "-m", "PyInstaller")
try {
    Invoke-WithArgs $pyinstallerBase @("--version") | Out-Null
} catch {
    throw "PyInstaller is not installed in the selected interpreter. Install it or omit -UseExistingPython."
}

$qtExcludes = @(
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DExtras",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DRender",
    "PySide6.QtAsyncio",
    "PySide6.QtBluetooth",
    "PySide6.QtCharts",
    "PySide6.QtConcurrent",
    "PySide6.QtDataVisualization",
    "PySide6.QtDesigner",
    "PySide6.QtGraphs",
    "PySide6.QtGraphsWidgets",
    "PySide6.QtHelp",
    "PySide6.QtHttpServer",
    "PySide6.QtLocation",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtNetworkAuth",
    "PySide6.QtNfc",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtPositioning",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.QtQuickControls2",
    "PySide6.QtQuickTest",
    "PySide6.QtQuickWidgets",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
    "PySide6.QtSensors",
    "PySide6.QtSerialBus",
    "PySide6.QtSerialPort",
    "PySide6.QtSpatialAudio",
    "PySide6.QtSql",
    "PySide6.QtStateMachine",
    "PySide6.QtSvg",
    "PySide6.QtSvgWidgets",
    "PySide6.QtTest",
    "PySide6.QtTextToSpeech",
    "PySide6.QtUiTools",
    "PySide6.QtWebChannel",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebSockets",
    "PySide6.QtWebView",
    "PySide6.QtXml",
    "PySide6.scripts",
    "PySide6.support"
)

$excludeArgs = @()
foreach ($module in $qtExcludes) {
    $excludeArgs += @("--exclude-module", $module)
}

$commonArgs = @(
    "--noconfirm",
    "--clean",
    "--paths", $projectRoot,
    "--hidden-import", "mpmath",
    "--collect-all", "mpmath",
    # emcee and corner sit behind ``HAS_EMCEE`` guards in
    # fitting.mcmc_fitter, so PyInstaller's static import graph won't
    # pick them up automatically; declare them explicitly so the bundled
    # .exe actually ships MCMC support.
    "--hidden-import", "emcee",
    "--hidden-import", "emcee.moves",
    "--hidden-import", "emcee.backends",
    "--collect-all", "emcee",
    "--hidden-import", "corner",
    "--collect-all", "corner"
) + $excludeArgs + $iconArgs + $dataArgs
$entryArgs = @($entryFile)

Write-Host "[5/6] Building onedir package..."
$onedirName = "DataLab"
Invoke-WithArgs $pyinstallerBase ($commonArgs + @("--windowed", "--name", $onedirName) + $entryArgs)

if (-not $SkipOneFile) {
    Write-Host "[5b/6] Building onefile package..."
    $onefileName = "DataLab"
    Invoke-WithArgs $pyinstallerBase ($commonArgs + @("--windowed", "--onefile", "--name", $onefileName) + $entryArgs)
}

if ($BuildInnoInstaller) {
    Write-Host "[5c/6] Building Inno Setup installer..."
    $appVersion = Get-ProjectVersion -PyprojectPath $pyprojectFile
    $env:DATALAB_APP_VERSION = $appVersion
    $env:DATALAB_WINDOWS_DIST_DIR = Join-Path $distDir $onedirName
    $env:DATALAB_WINDOWS_INSTALLER_DIR = $distDir

    if (-not (Test-Path $env:DATALAB_WINDOWS_DIST_DIR -PathType Container)) {
        throw "PyInstaller onedir output not found: $env:DATALAB_WINDOWS_DIST_DIR"
    }

    $iscc = Resolve-InnoSetupCompiler -PathOverride $InnoSetupPath
    Invoke-WithArgs @($iscc) @((Join-Path $projectRoot "packaging\windows\DataLab.iss"))
}

Write-Host "[6/6] Windows packaging complete."
Write-Host ("onedir output : {0}" -f (Join-Path $distDir $onedirName))
if (-not $SkipOneFile) {
    Write-Host ("onefile output: {0}" -f (Join-Path $distDir ("{0}.exe" -f $onefileName)))
}
if ($BuildInnoInstaller) {
    Write-Host ("installer    : {0}" -f (Join-Path $distDir ("DataLab-{0}-Windows-x64.exe" -f $env:DATALAB_APP_VERSION)))
}
Write-Host "Distribute the contents of dist/ to end users; Python and all dependencies are bundled."
