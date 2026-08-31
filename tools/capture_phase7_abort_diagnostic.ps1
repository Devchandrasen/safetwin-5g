param(
    [string]$Run = "evidence/scenarios/20260825T045337Z-phase7-campaign-v2a",
    [string]$OutputRoot = "evidence/environment",
    [string]$EventTimestamp = "20260825T092639Z"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$runPath = if ([System.IO.Path]::IsPathRooted($Run)) { $Run } else { Join-Path $root $Run }
$output = Join-Path $root "$OutputRoot/$EventTimestamp-phase7-abort-diagnostic"
$dockerLogRoot = Join-Path $env:LOCALAPPDATA "Docker/log/host"
$failedUnitId = "safetwin5g-phase7-brace-v2a-test-cpu_saturation-2-observe_only-1309"
$failedTracePath = Join-Path $runPath "units/$failedUnitId.json"
$containerNames = @(
    "safetwin5g-open5gs",
    "safetwin5g-gnb",
    "safetwin5g-ue",
    "safetwin5g-mongodb",
    "safetwin5g-prometheus"
)

function Write-Utf8Lf {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Content
    )
    $normalized = $Content.Replace("`r`n", "`n").Replace("`r", "`n")
    if (-not $normalized.EndsWith("`n")) { $normalized += "`n" }
    [System.IO.File]::WriteAllText(
        $Path,
        $normalized,
        [System.Text.UTF8Encoding]::new($false)
    )
}

if (-not (Test-Path -LiteralPath $runPath -PathType Container)) {
    throw "campaign directory not found: $runPath"
}
if (-not (Test-Path -LiteralPath $failedTracePath -PathType Leaf)) {
    throw "failed trace not found: $failedTracePath"
}
if (Test-Path -LiteralPath $output) {
    throw "refusing to overwrite diagnostic: $output"
}

$summary = Get-Content -Raw -LiteralPath (Join-Path $runPath "summary.json") | ConvertFrom-Json
$trace = Get-Content -Raw -LiteralPath $failedTracePath | ConvertFrom-Json
$failedChecks = @(
    $trace.checks.PSObject.Properties |
        Where-Object { -not $_.Value } |
        ForEach-Object { $_.Name }
)

$logFiles = @(
    Get-ChildItem -LiteralPath $dockerLogRoot -File -Filter "com.docker.backend.exe.log*" |
        Sort-Object FullName
)
$eventLines = @()
$sourceLogs = @()
foreach ($log in $logFiles) {
    $matches = @(
        Get-Content -LiteralPath $log.FullName |
            Where-Object {
                $_ -match '^\[2026-08-25T09:26:(39|40|41|42)\.' -and
                $_ -match 'compose/bulk/:action|ProjectName:safetwin5g-sandbox|ContainerStopComposeLinux|exposer\.Remove'
            }
    )
    if ($matches.Count -gt 0) {
        $sourceLogs += [ordered]@{
            path = $log.FullName
            sha256 = (Get-FileHash -LiteralPath $log.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        }
        $eventLines += $matches
    }
}
if (-not ($eventLines -match 'POST /compose/bulk/:action')) {
    throw "Docker Desktop compose-stop event was not found in archived logs"
}

$containers = @()
foreach ($name in $containerNames) {
    $inspection = docker inspect $name | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw "docker inspect failed: $name" }
    $containers += [ordered]@{
        name = $inspection.Name.TrimStart("/")
        image = $inspection.Config.Image
        state = $inspection.State.Status
        exit_code = $inspection.State.ExitCode
        oom_killed = $inspection.State.OOMKilled
        started_at = $inspection.State.StartedAt
        finished_at = $inspection.State.FinishedAt
        restart_count = $inspection.RestartCount
    }
}

New-Item -ItemType Directory -Path $output | Out-Null
Write-Utf8Lf (Join-Path $output "docker-compose-stop.log") ($eventLines -join "`n")

$diagnostic = [ordered]@{
    schema_version = 1
    event_id = "phase7-campaign-abort-1"
    captured_at = (Get-Date).ToUniversalTime().ToString("o")
    source_run = $summary.run_id
    source_run_manifest_sha256 = (Get-FileHash -LiteralPath (Join-Path $runPath "manifest.json") -Algorithm SHA256).Hash.ToLowerInvariant()
    source_run_passed = $summary.passed
    planned_unit_count = $summary.planned_unit_count
    completed_unit_count = $summary.completed_unit_count
    passed_unit_count = $summary.passed_unit_count
    aborted_for_cleanup = $summary.aborted_for_cleanup
    failed_unit = [ordered]@{
        unit_id = $failedUnitId
        trace_sha256 = (Get-FileHash -LiteralPath $failedTracePath -Algorithm SHA256).Hash.ToLowerInvariant()
        cleanup_completed = $trace.cleanup_completed
        cleanup_verified = $trace.cleanup_verified
        errors = @($trace.errors)
        failed_checks = $failedChecks
        recovery_sample_count = @($trace.windows.recovery.samples).Count
    }
    docker_desktop_event = [ordered]@{
        observed = $true
        endpoint = "POST /compose/bulk/:action"
        project_name = "safetwin5g-sandbox"
        event_started_at = "2026-08-25T09:26:39.148249600Z"
        interpretation = "Docker Desktop initiated a Compose-project stop while the campaign was running."
        source_logs = $sourceLogs
    }
    container_exit_states = $containers
    admissibility = [ordered]@{
        campaign_complete = $false
        dataset_release_eligible = $false
        outcome_analysis_eligible = $false
        failed_trace_reusable = $false
        resume_permitted = $false
        required_recovery = "Preserve this failed run and execute a new full preregistered campaign from a clean stack."
    }
    claim_boundaries = [ordered]@{
        evidence_type = "sandbox operational failure"
        radio_access = "simulated"
        hardware = "not measured"
        operator_validation = "not performed"
        publication_result = "not evaluated"
    }
}
Write-Utf8Lf (Join-Path $output "diagnostic.json") ($diagnostic | ConvertTo-Json -Depth 9)

$captured = @{}
Get-ChildItem -LiteralPath $output -File | ForEach-Object {
    $captured[$_.Name] = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
}
$manifest = [ordered]@{
    schema_version = 1
    run_id = Split-Path -Leaf $output
    passed = $true
    scope = "read-only diagnosis of an inadmissible aborted campaign"
    source_campaign_passed = $false
    outcome_analysis_performed = $false
    captured_file_sha256 = $captured
}
Write-Utf8Lf (Join-Path $output "manifest.json") ($manifest | ConvertTo-Json -Depth 6)

Write-Output "PASS: Phase 7 abort diagnostic captured"
Write-Output "EVIDENCE=$output"
