$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
$env:PYTHONPATH = Join-Path $repoRoot 'src'

& $python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) {
    throw "Repository tests failed with exit code $LASTEXITCODE"
}

& $python -c "from pathlib import Path; from safetwin5g.phase7_design import load_phase7_design,expand_phase7_design; d=load_phase7_design(Path('config/experiments/phase7-brace-v2a.json')); u=expand_phase7_design(d); faulty={x['assignment_block_id'] for x in u if x['split']=='test' and x['fault_family']!='no_fault'}; upper=1-.05**(1/30); assert len(u)==675 and len(faulty)==60 and upper<.10; print(f'phase7_v2a_valid units={len(u)} faulty_test_blocks={len(faulty)} zero_violation_upper_n30={upper:.6f}')"
if ($LASTEXITCODE -ne 0) {
    throw "Phase 7 amendment precision check failed with exit code $LASTEXITCODE"
}
