$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
$env:PYTHONPATH = Join-Path $repoRoot 'src'

& $python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) {
    throw "Repository tests failed with exit code $LASTEXITCODE"
}

& $python -c "from pathlib import Path; from safetwin5g.phase7_design import load_phase7_design, expand_phase7_design; d=load_phase7_design(Path('config/experiments/phase7-brace-v2.json')); u=expand_phase7_design(d); b={x['assignment_block_id'] for x in u}; print(f'phase7_design_valid blocks={len(b)} units={len(u)}')"
if ($LASTEXITCODE -ne 0) {
    throw "Phase 7 design validation failed with exit code $LASTEXITCODE"
}
