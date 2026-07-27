Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = (Resolve-Path (Join-Path $ScriptDir "..")).Path

if ($env:HASC_PYTHON -and $env:HASC_PYTHON.Trim().Length -gt 0) {
    $PythonBin = $env:HASC_PYTHON
} elseif (Test-Path (Join-Path $Root ".venv\Scripts\python.exe")) {
    $PythonBin = (Join-Path $Root ".venv\Scripts\python.exe")
} elseif (Test-Path (Join-Path $Root "venv\Scripts\python.exe")) {
    $PythonBin = (Join-Path $Root "venv\Scripts\python.exe")
} else {
    $PythonBin = "python"
}

$target = if ($env:VBCC_TARGET -and $env:VBCC_TARGET.Trim().Length -gt 0) { $env:VBCC_TARGET } else { "aos68k" }

Write-Host "Running HAS<->vbcc interop tests"
Write-Host "  root: $Root"
Write-Host "  python: $PythonBin"
Write-Host "  vbcc target: $target"

Push-Location $Root
try {
    & $PythonBin -m pytest tests/test_vbcc_interop.py -v
}
finally {
    Pop-Location
}
