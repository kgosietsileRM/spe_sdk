param(
    [switch]$Reinstall
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if ($Reinstall -and (Test-Path -LiteralPath (Join-Path $PSScriptRoot ".venv"))) {
    Remove-Item -LiteralPath (Join-Path $PSScriptRoot ".venv") -Recurse -Force
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) {
        & py -3.12 -m venv .venv
    }
    else {
        & python -m venv .venv
    }
    if (-not (Test-Path -LiteralPath $venvPython)) {
        throw "Could not create the demo virtual environment."
    }
}

& $venvPython -m pip install --quiet --upgrade pip
$wheel = Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot "..\assets") -Filter "spe_sdk-*.whl" |
    Sort-Object Name -Descending |
    Select-Object -First 1
if (-not $wheel) {
    throw "No spe_sdk wheel found in examples/assets. Build it with 'python -m build' first."
}
& $venvPython -m pip install --quiet $wheel.FullName
if (Test-Path -LiteralPath (Join-Path $PSScriptRoot "requirements.txt")) {
    & $venvPython -m pip install --quiet -r requirements.txt
}

& $venvPython -c "import spe, sys; print(f'independent env: Python {sys.version.split()[0]}, spe {spe.__version__} from {spe.__file__}')"
