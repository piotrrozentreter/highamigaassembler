param(
    [string]$NegManifest = "examples/tests/compiler/negative_examples.txt",
    [string]$PythonBin = "",
    [string]$OutputAsm = "tmp/has_examples_split.s"
)

$ErrorActionPreference = "Stop"
if (Get-Variable PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $false
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = (Resolve-Path (Join-Path $scriptDir "..\..")).Path.TrimEnd('\\')
$manifestPath = Join-Path $root $NegManifest

if (-not $PythonBin) {
    if ($env:HASC_PYTHON -and $env:HASC_PYTHON.Trim().Length -gt 0) {
        $PythonBin = $env:HASC_PYTHON
    }
    elseif (Test-Path (Join-Path $root ".venv\Scripts\python.exe")) {
        $PythonBin = (Join-Path $root ".venv\Scripts\python.exe")
    }
    elseif (Test-Path (Join-Path $root "venv\Scripts\python.exe")) {
        $PythonBin = (Join-Path $root "venv\Scripts\python.exe")
    }
    else {
        $PythonBin = "python"
    }
}

if (-not (Test-Path $manifestPath)) {
    Write-Error "negative manifest not found: $manifestPath"
    exit 2
}

$negExpected = [System.Collections.Generic.Dictionary[string,string]]::new([System.StringComparer]::OrdinalIgnoreCase)

Get-Content $manifestPath | ForEach-Object {
    $line = $_
    if ($line -match '#') {
        $line = $line.Substring(0, $line.IndexOf('#'))
    }
    $line = $line.Trim()
    if (-not $line) {
        return
    }

    $parts = $line -split '\|', 2
    $path = $parts[0].Trim().Replace('\', '/')
    $expected = if ($parts.Length -gt 1) { $parts[1].Trim() } else { "failure" }
    if (-not $expected) {
        $expected = "failure"
    }

    $negExpected[$path] = $expected
}

if ($negExpected.Count -eq 0) {
    Write-Error "no entries in negative manifest: $manifestPath"
    exit 2
}

$total = 0
$posTotal = 0
$posOk = 0
$posFail = 0
$negTotal = 0
$negOk = 0
$negFail = 0

$outDir = Split-Path -Parent $OutputAsm
if ($outDir) {
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null
}

Write-Output "Running example split check"
Write-Output "  root: $root"
Write-Output "  python: $PythonBin"
Write-Output "  negative manifest: $NegManifest"
Write-Output ""

$examples = Get-ChildItem (Join-Path $root "examples\tests\compiler") -Filter *.has -Recurse | Sort-Object FullName
foreach ($f in $examples) {
    $rel = $f.FullName.Substring($root.Length + 1).Replace('\', '/')

    # Include snippets are not standalone programs.
    if ($rel.StartsWith("examples/includes/")) {
        continue
    }

    $total++

    $cmd = '"{0}" -m hasc.cli "{1}" -o "{2}" >NUL 2>&1' -f $PythonBin, $rel, $OutputAsm
    cmd /c $cmd | Out-Null
    $compileOk = ($LASTEXITCODE -eq 0)

    if ($negExpected.ContainsKey($rel)) {
        $negTotal++
        if (-not $compileOk) {
            $negOk++
            Write-Output ("NEG OK   {0} ({1})" -f $rel, $negExpected[$rel])
        }
        else {
            $negFail++
            Write-Output ("NEG FAIL {0} expected failure but compiled" -f $rel)
        }
    }
    else {
        $posTotal++
        if ($compileOk) {
            $posOk++
            Write-Output ("POS OK   {0}" -f $rel)
        }
        else {
            $posFail++
            Write-Output ("POS FAIL {0}" -f $rel)
        }
    }
}

Write-Output ""
Write-Output "Summary"
Write-Output ("  scanned: {0}" -f $total)
Write-Output ("  positive: total={0} ok={1} fail={2}" -f $posTotal, $posOk, $posFail)
Write-Output ("  negative: total={0} ok={1} fail={2}" -f $negTotal, $negOk, $negFail)

if ($posFail -ne 0 -or $negFail -ne 0) {
    exit 1
}

exit 0
