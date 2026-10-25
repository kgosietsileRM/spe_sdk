param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Arguments
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) {
    & (Join-Path $PSScriptRoot "bootstrap.ps1")
}

& $venvPython (Join-Path $PSScriptRoot "spe_cli.py") @Arguments
