param(
    [string]$OutputRoot = "evidence/verification"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv/Scripts/python.exe"
$stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$output = Join-Path $root "$OutputRoot/$stamp-dataset-v2a-builder"
New-Item -ItemType Directory -Path $output | Out-Null

Push-Location $root
try {
    & $python -m pytest tests/test_dataset_v2a.py -q *>&1 |
        Tee-Object -FilePath (Join-Path $output "targeted-tests.log")
    if ($LASTEXITCODE -ne 0) { throw "targeted dataset v2a tests failed" }

    & $python -m pytest -q *>&1 |
        Tee-Object -FilePath (Join-Path $output "full-tests.log")
    if ($LASTEXITCODE -ne 0) { throw "full test suite failed" }

    & $python -m compileall -q src tools *>&1 |
        Tee-Object -FilePath (Join-Path $output "compileall.log")
    if ($LASTEXITCODE -ne 0) { throw "compileall failed" }

    $files = @(
        "src/safetwin5g/dataset_v2a.py",
        "tests/test_dataset_v2a.py",
        "tools/build_dataset_v2a.py",
        "tools/audit_dataset_v2a.py",
        "docs/DATASET_V2A_CONTRACT.md",
        "evidence/scenarios/20260825T044909Z-phase7-pilot-v2a/manifest.json"
    )
    $hashes = @{}
    foreach ($file in $files) {
        $hashes[$file] = (Get-FileHash -LiteralPath (Join-Path $root $file) -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $report = [ordered]@{
        schema_version = 1
        passed = $true
        scope = "dataset-v2a-builder-and-public-safety-contract"
        source = "complete-block-runner-pilot-only"
        release_eligible = $false
        evidence_label = "sandbox-measured"
        radio_evidence_label = "simulated"
        hardware_evidence_label = $null
        operator_validation = $false
        test_labels_opened = $false
        files_sha256 = $hashes
    }
    $report | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $output "verification.json") -Encoding utf8
    Write-Output "PASS: dataset v2a builder verified; full release remains gated on the 675-unit campaign"
    Write-Output "EVIDENCE=$output"
}
finally {
    Pop-Location
}
