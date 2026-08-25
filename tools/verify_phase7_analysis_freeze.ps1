param(
    [string]$OutputRoot = "evidence/verification"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv/Scripts/python.exe"
$lockPath = Join-Path $root "config/experiments/phase7-analysis-v2a-lock.json"
$stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$output = Join-Path $root "$OutputRoot/$stamp-phase7-analysis-freeze"
New-Item -ItemType Directory -Path $output | Out-Null

Push-Location $root
try {
    & $python -m pytest tests/test_analysis_v2a.py -q *>&1 |
        Tee-Object -FilePath (Join-Path $output "targeted-tests.log")
    if ($LASTEXITCODE -ne 0) { throw "targeted Phase 7 analysis tests failed" }

    & $python -m pytest -q *>&1 |
        Tee-Object -FilePath (Join-Path $output "full-tests.log")
    if ($LASTEXITCODE -ne 0) { throw "full test suite failed" }

    & $python -m compileall -q src tools
    if ($LASTEXITCODE -ne 0) { throw "compileall failed" }

    $lock = Get-Content -LiteralPath $lockPath -Raw | ConvertFrom-Json
    foreach ($item in $lock.files) {
        $actual = (Get-FileHash -LiteralPath (Join-Path $root $item.path) -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne $item.sha256) { throw "analysis lock mismatch: $($item.path)" }
    }
    $report = [ordered]@{
        schema_version = 1
        passed = $true
        scope = "phase7-sealed-analysis-code-and-hashes"
        lock_sha256 = (Get-FileHash -LiteralPath $lockPath -Algorithm SHA256).Hash.ToLowerInvariant()
        test_labels_opened = $false
        model_selection = "train-block leave-one-block-out only"
        calibration_use = "uncertainty calibration only"
        required_test_blocks = 70
        required_faulty_test_blocks = 60
        g3_paired_test_blocks = 70
        multiplicity = "Holm for G2 and G3"
        evidence_label = "fixture-and-synthetic-tests-only"
    }
    $report | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $output "verification.json") -Encoding utf8
    Write-Output "PASS: Phase 7 analysis code and hashes frozen before test-label opening"
    Write-Output "EVIDENCE=$output"
}
finally {
    Pop-Location
}
