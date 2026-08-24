$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
$env:PYTHONPATH = Join-Path $repoRoot 'src'

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Program,
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$Arguments
    )
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Program failed with exit code $LASTEXITCODE"
    }
}

Invoke-Checked $python tools/audit_phase6_pilot.py `
    --pilot evidence/scenarios/20260824T073851Z-phase6-pilot-v1
Invoke-Checked $python sandbox/run_phase6.py --dry-run
Invoke-Checked $python -m unittest discover -s tests -v
