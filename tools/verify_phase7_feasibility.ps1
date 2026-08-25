$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
$env:PYTHONPATH = Join-Path $repoRoot 'src'

& $python tools/audit_phase7_feasibility.py `
    --benchmark evidence/benchmarks/20260825T044022Z-phase7-v1-feasibility
if ($LASTEXITCODE -ne 0) {
    throw "Phase 7 feasibility audit failed with exit code $LASTEXITCODE"
}

& $python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) {
    throw "Repository tests failed with exit code $LASTEXITCODE"
}
