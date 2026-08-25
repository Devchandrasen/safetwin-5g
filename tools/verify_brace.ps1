$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
$env:PYTHONPATH = Join-Path $repoRoot 'src'

& $python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) {
    throw "Repository tests failed with exit code $LASTEXITCODE"
}

& $python -c "from safetwin5g.brace import BlockConformalCalibration; a=('a','b'); blocks={f'b{i}':{x:(10.0,10.0+i/10) for x in a} for i in range(1,22)}; c=BlockConformalCalibration.fit(blocks,action_ids=a,coverage=.9); assert c.status=='finite' and c.rank==20 and c.calibration_block_n==21; print(c.guarantee_contract())"
if ($LASTEXITCODE -ne 0) {
    throw "BRACE contract check failed with exit code $LASTEXITCODE"
}
