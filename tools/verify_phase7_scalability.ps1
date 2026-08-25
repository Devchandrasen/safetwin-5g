param(
    [string]$Benchmark = "evidence/benchmarks/20260825T051037Z-phase7-brace-scalability",
    [string]$OutputRoot = "evidence/verification"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv/Scripts/python.exe"
$stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$output = Join-Path $root "$OutputRoot/$stamp-phase7-scalability"
New-Item -ItemType Directory -Path $output | Out-Null

Push-Location $root
try {
    & $python -m pytest tests/test_phase7_scalability.py -q *>&1 |
        Tee-Object -FilePath (Join-Path $output "targeted-tests.log")
    if ($LASTEXITCODE -ne 0) { throw "scalability tests failed" }

    & $python tools/audit_phase7_scalability.py --benchmark $Benchmark *>&1 |
        Tee-Object -FilePath (Join-Path $output "artifact-audit.log")
    if ($LASTEXITCODE -ne 0) { throw "scalability artifact audit failed" }

    $reportPath = Join-Path $root "$Benchmark/report.json"
    $report = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
    $verification = [ordered]@{
        schema_version = 1
        passed = $true
        benchmark = $Benchmark
        benchmark_manifest_sha256 = (Get-FileHash -LiteralPath (Join-Path $root "$Benchmark/manifest.json") -Algorithm SHA256).Hash.ToLowerInvariant()
        block_sizes = @($report.calibration | ForEach-Object { $_.block_n })
        empirical_log_log_slope = $report.empirical_log_log_slope
        median_microseconds_per_proposal = $report.decision_batch.median_microseconds_per_proposal
        input_evidence_label = "fixture"
        runtime_measurement = "local-host-measured"
        network_performance_claim = $false
        hardware_or_operator_claim = $false
        apply_allowed = $false
    }
    $verification | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $output "verification.json") -Encoding utf8
    Write-Output "PASS: Phase 7 BRACE scalability artifact verified with bounded fixture claims"
    Write-Output "EVIDENCE=$output"
}
finally {
    Pop-Location
}
