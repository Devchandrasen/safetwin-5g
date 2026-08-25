$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
$env:PYTHONPATH = Join-Path $repoRoot 'src'

& $python tools/audit_phase7_run.py `
    --run evidence/scenarios/20260825T044909Z-phase7-pilot-v2a `
    --expected-units 5 `
    --expected-blocks 1
if ($LASTEXITCODE -ne 0) {
    throw "Phase 7 pilot audit failed with exit code $LASTEXITCODE"
}

& $python sandbox/run_phase7.py --dry-run
if ($LASTEXITCODE -ne 0) {
    throw "Phase 7 full dry-run failed with exit code $LASTEXITCODE"
}

& $python sandbox/run_phase7.py --pilot-blocks 1 --dry-run
if ($LASTEXITCODE -ne 0) {
    throw "Phase 7 pilot dry-run failed with exit code $LASTEXITCODE"
}

& $python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) {
    throw "Repository tests failed with exit code $LASTEXITCODE"
}
