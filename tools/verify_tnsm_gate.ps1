param(
    [string]$OutputRoot = "evidence/verification"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv/Scripts/python.exe"
$stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$output = Join-Path $root "$OutputRoot/$stamp-tnsm-manuscript-gate"
New-Item -ItemType Directory -Path $output | Out-Null

Push-Location $root
try {
    & $python -m pytest tests/test_tnsm_gate.py tests/test_phase7_provenance.py -q *>&1 |
        Tee-Object -FilePath (Join-Path $output "targeted-tests.log")
    if ($LASTEXITCODE -ne 0) { throw "TNSM gate tests failed" }

    & $python -m pytest -q *>&1 |
        Tee-Object -FilePath (Join-Path $output "full-tests.log")
    if ($LASTEXITCODE -ne 0) { throw "full test suite failed" }

    $files = @(
        "src/safetwin5g/tnsm_gate.py",
        "src/safetwin5g/phase7_provenance.py",
        "tests/test_tnsm_gate.py",
        "tools/run_tnsm_manuscript_gate.py",
        "tools/verify_phase7_end_to_end.ps1"
    )
    $hashes = @{}
    foreach ($file in $files) {
        $hashes[$file] = (Get-FileHash -LiteralPath (Join-Path $root $file) -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $report = [ordered]@{
        schema_version = 1
        passed = $true
        scope = "fail-closed-local-TNSM-manuscript-gate"
        actual_gate_evaluated = $false
        actual_gate_pending_reason = "fresh campaign, release, analysis, and actual provenance audit are incomplete"
        baseline_win_blocks_positive_draft = $true
        claim_tier_promotion_blocks_positive_draft = $true
        missing_D1_disclosure_blocks_positive_draft = $true
        publication_submission = "pending-external-authorization"
        live_actuation = "no-go"
        evidence_label = "fixture"
        files_sha256 = $hashes
    }
    $json = ($report | ConvertTo-Json -Depth 5).Replace("`r`n", "`n").Replace("`r", "`n") + "`n"
    [System.IO.File]::WriteAllText(
        (Join-Path $output "verification.json"),
        $json,
        [System.Text.UTF8Encoding]::new($false)
    )
    Write-Output "PASS: local TNSM manuscript gate is fail-closed; actual decision remains pending"
    Write-Output "EVIDENCE=$output"
}
finally {
    Pop-Location
}
