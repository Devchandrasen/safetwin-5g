param(
    [string]$OutputRoot = "evidence/verification",
    [string]$Diagnostic = "evidence/environment/20260831T094658Z-phase7-host-sleep-abort-diagnostic",
    [string]$SourceRun = "evidence/scenarios/20260831T052237Z-phase7-campaign-v2a"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv/Scripts/python.exe"
$stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$output = Join-Path $root "$OutputRoot/$stamp-phase7-host-resilience"
$diagnosticPath = Join-Path $root $Diagnostic
$sourceRunPath = Join-Path $root $SourceRun

function Write-Utf8Lf {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Content
    )
    $normalized = $Content.Replace("`r`n", "`n").Replace("`r", "`n")
    if (-not $normalized.EndsWith("`n")) { $normalized += "`n" }
    [IO.File]::WriteAllText($Path, $normalized, [Text.UTF8Encoding]::new($false))
}

function Get-PortableTextSha256 {
    param([Parameter(Mandatory = $true)][string]$Path)
    $content = [IO.File]::ReadAllText($Path)
    $normalized = $content.Replace("`r`n", "`n").Replace("`r", "`n")
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes($normalized)
    $sha256 = [Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($sha256.ComputeHash($bytes))).Replace("-", "").ToLowerInvariant()
    }
    finally {
        $sha256.Dispose()
    }
}

New-Item -ItemType Directory -Path $output | Out-Null
Push-Location $root
try {
    $probe = & "$root/tools/run_with_sleep_inhibition.ps1" -FilePath "powershell.exe" -ProbeOnly *>&1
    $probeText = $probe -join "`n"
    Write-Utf8Lf (Join-Path $output "sleep-inhibition-probe.log") $probeText
    if ($LASTEXITCODE -ne 0 -or $probeText -notmatch "PROBE=PASS" -or $probeText -notmatch "SLEEP_INHIBITION_CLEARED=true") {
        throw "sleep-inhibition probe failed"
    }

    $targeted = & $python -m pytest tests/test_phase7_host_resilience.py -q *>&1
    $targetedText = $targeted -join "`n"
    Write-Utf8Lf (Join-Path $output "targeted-tests.log") $targetedText
    if ($LASTEXITCODE -ne 0) { throw "host-resilience tests failed" }

    $full = & $python -m pytest -q *>&1
    $fullText = $full -join "`n"
    Write-Utf8Lf (Join-Path $output "full-tests.log") $fullText
    if ($LASTEXITCODE -ne 0) { throw "full test suite failed" }

    $audit = & $python tools/audit_phase7_host_sleep_abort.py `
        --diagnostic $diagnosticPath --source-run $sourceRunPath *>&1
    $auditText = $audit -join "`n"
    Write-Utf8Lf (Join-Path $output "abort-audit.json") $auditText
    if ($LASTEXITCODE -ne 0) { throw "host-sleep abort audit failed" }
    $auditObject = $auditText | ConvertFrom-Json
    if (-not $auditObject.passed) { throw "host-sleep abort audit did not pass" }

    & $python -m compileall -q src tools
    if ($LASTEXITCODE -ne 0) { throw "compileall failed" }

    $files = @(
        "tools/run_with_sleep_inhibition.ps1",
        "tools/capture_phase7_host_sleep_abort.ps1",
        "tools/audit_phase7_host_sleep_abort.py",
        "tools/verify_phase7_host_resilience.ps1",
        "tests/test_phase7_host_resilience.py"
    )
    $hashes = [ordered]@{}
    foreach ($file in $files) {
        $hashes[$file] = Get-PortableTextSha256 (Join-Path $root $file)
    }
    $report = [ordered]@{
        schema_version = 1
        passed = $true
        scope = "phase7-host-sleep-abort-and-rerun-resilience"
        source_campaign_complete = $false
        source_campaign_outcome_analysis_performed = $false
        source_campaign_completed_trace_count = $auditObject.completed_trace_count
        source_campaign_last_progress_line = $auditObject.last_progress_line
        host_sleep_event_verified = $true
        sleep_inhibition_probe_passed = $true
        sleep_inhibition_flags = @("ES_CONTINUOUS", "ES_SYSTEM_REQUIRED")
        display_required = $false
        away_mode_required = $false
        explicit_user_sleep_override_claimed = $false
        fresh_campaign_required = $true
        resume_permitted = $false
        files_sha256 = $hashes
        files_sha256_mode = "utf8-lf-normalized"
        evidence_label = "sandbox operational interruption and local host-control verification"
    }
    Write-Utf8Lf (Join-Path $output "verification.json") ($report | ConvertTo-Json -Depth 6)

    $captured = [ordered]@{}
    Get-ChildItem -LiteralPath $output -File | Sort-Object Name | ForEach-Object {
        $captured[$_.Name] = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $manifest = [ordered]@{
        schema_version = 1
        run_id = Split-Path -Leaf $output
        passed = $true
        captured_file_sha256 = $captured
    }
    Write-Utf8Lf (Join-Path $output "manifest.json") ($manifest | ConvertTo-Json -Depth 5)

    Write-Output "PASS: Phase 7 host-resilience verification"
    Write-Output "EVIDENCE=$output"
}
finally {
    Pop-Location
}
