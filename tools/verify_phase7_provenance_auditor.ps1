param(
    [string]$OutputRoot = "evidence/verification"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv/Scripts/python.exe"
$stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$output = Join-Path $root "$OutputRoot/$stamp-phase7-provenance-auditor"
New-Item -ItemType Directory -Path $output | Out-Null

Push-Location $root
try {
    & $python -m pytest tests/test_phase7_provenance.py -q *>&1 |
        Tee-Object -FilePath (Join-Path $output "targeted-tests.log")
    if ($LASTEXITCODE -ne 0) { throw "Phase 7 provenance tests failed" }

    & $python -m pytest -q *>&1 |
        Tee-Object -FilePath (Join-Path $output "full-tests.log")
    if ($LASTEXITCODE -ne 0) { throw "full test suite failed" }

    $files = @(
        "src/safetwin5g/phase7_provenance.py",
        "tests/test_phase7_provenance.py",
        "tools/audit_phase7_end_to_end.py",
        "tools/verify_phase7_end_to_end.ps1"
    )
    $hashes = @{}
    foreach ($file in $files) {
        $hashes[$file] = (Get-FileHash -LiteralPath (Join-Path $root $file) -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $report = [ordered]@{
        schema_version = 1
        passed = $true
        scope = "phase7-cross-artifact-provenance-auditor"
        actual_chain_executed = $false
        actual_chain_pending_reason = "fresh 675-unit campaign is still running"
        synthetic_hash_break_rejected = $true
        synthetic_claim_tier_promotion_rejected = $true
        files_sha256 = $hashes
        evidence_label = "fixture"
    }
    $report | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $output "verification.json") -Encoding utf8
    Write-Output "PASS: Phase 7 provenance auditor verified against positive and fail-closed fixtures"
    Write-Output "EVIDENCE=$output"
}
finally {
    Pop-Location
}
