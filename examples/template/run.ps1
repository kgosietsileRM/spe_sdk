param(
    [switch]$Reinstall
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if ($Reinstall -or -not (Test-Path -LiteralPath $venvPython)) {
    & (Join-Path $PSScriptRoot "bootstrap.ps1") -Reinstall:$Reinstall
}

Write-Host "Template studio: http://127.0.0.1:5001"
& $venvPython (Join-Path $PSScriptRoot "app.py")
