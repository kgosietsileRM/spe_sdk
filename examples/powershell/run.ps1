param(
    [ValidateSet("local", "server")]
    [string]$Mode = "local",
    [int]$Frames = 60,
    [double]$Fps = 5.0,
    [string]$Out = "outputs",
    [string]$Url = "http://127.0.0.1:5000",
    [string]$Model = "model-a",
    [string[]]$Sources = @("video"),
    [switch]$Reinstall,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Extra
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if ($Reinstall -or -not (Test-Path -LiteralPath $venvPython)) {
    & (Join-Path $PSScriptRoot "bootstrap.ps1") -Reinstall:$Reinstall
}

$batchArgs = @(
    "--mode", $Mode,
    "--frames", "$Frames",
    "--fps", "$Fps",
    "--out", $Out,
    "--url", $Url,
    "--model", $Model,
    "--sources"
) + $Sources + $Extra

& (Join-Path $PSScriptRoot "analyze.bat") @batchArgs
exit $LASTEXITCODE
