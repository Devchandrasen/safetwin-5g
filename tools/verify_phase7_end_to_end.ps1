param(
    [Parameter(Mandatory = $true)][string]$Campaign,
    [Parameter(Mandatory = $true)][string]$Dataset,
    [Parameter(Mandatory = $true)][string]$Analysis,
    [string]$Scalability = "evidence/benchmarks/20260825T051037Z-phase7-brace-scalability",
    [string]$OutputRoot = "evidence/verification"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv/Scripts/python.exe"
$stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$output = Join-Path $root "$OutputRoot/$stamp-phase7-end-to-end"
New-Item -ItemType Directory -Path $output | Out-Null

function Invoke-Audit {
    param([string]$Name, [string[]]$Arguments)
    & $python @Arguments *>&1 | Tee-Object -FilePath (Join-Path $output "$Name.log")
    if ($LASTEXITCODE -ne 0) { throw "$Name failed" }
}

Push-Location $root
try {
    Invoke-Audit "campaign-audit" @("tools/audit_phase7_run.py", "--run", $Campaign, "--expected-units", "675", "--expected-blocks", "135")
    Invoke-Audit "dataset-audit" @("tools/audit_dataset_v2a.py", "--release", $Dataset)
    Invoke-Audit "analysis-audit" @("tools/audit_phase7_analysis.py", "--analysis", $Analysis)
    Invoke-Audit "scalability-audit" @("tools/audit_phase7_scalability.py", "--benchmark", $Scalability)
    Invoke-Audit "provenance-audit" @("tools/audit_phase7_end_to_end.py", "--campaign", $Campaign, "--dataset", $Dataset, "--analysis", $Analysis, "--scalability", $Scalability)

    & $python -m pytest -q *>&1 | Tee-Object -FilePath (Join-Path $output "full-tests.log")
    if ($LASTEXITCODE -ne 0) { throw "full test suite failed" }

    $analysisReport = Get-Content -LiteralPath (Join-Path $root "$Analysis/report.json") -Raw | ConvertFrom-Json
    $verification = [ordered]@{
        schema_version = 1
        passed = $true
        campaign = $Campaign
        dataset = $Dataset
        analysis = $Analysis
        scalability = $Scalability
        TNSM_claim_gate = $analysisReport.decision.TNSM_claim_gate
        live_actuation = "no-go"
        submission_authorized = $false
        evidence_label = "sandbox-measured"
        radio_evidence_label = "simulated"
        hardware_evidence_label = $null
        operator_validation = $false
        environment_deviation_D1_disclosed = $true
        procedural_outcome_seal = $true
        cryptographic_blinding = $false
    }
    $verification | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $output "verification.json") -Encoding utf8
    Write-Output "PASS: complete Phase 7 artifact chain independently verified"
    Write-Output "EVIDENCE=$output"
}
finally {
    Pop-Location
}
