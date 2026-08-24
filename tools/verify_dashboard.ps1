$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $PSScriptRoot
$dashboard = Join-Path $repoRoot 'dashboard'
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'

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

Invoke-Checked $python tools/export_product_snapshot.py --check

Push-Location -LiteralPath $dashboard
try {
    Invoke-Checked npm ci
    Invoke-Checked npm run build
    Invoke-Checked npm run lint
    Invoke-Checked npm audit
}
finally {
    Pop-Location
}

Invoke-Checked $python -m unittest discover -s tests -v
