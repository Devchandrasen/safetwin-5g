param(
    [string]$Run = "evidence/scenarios/20260831T052237Z-phase7-campaign-v2a",
    [string]$StdoutLog = "$env:LOCALAPPDATA/Temp/safetwin-phase7-campaign-20260831T052236Z.stdout.log",
    [string]$StderrLog = "$env:LOCALAPPDATA/Temp/safetwin-phase7-campaign-20260831T052236Z.stderr.log",
    [string]$OutputRoot = "evidence/environment",
    [string]$EventTimestamp = "20260831T094658Z",
    [int]$CampaignPid = 38664,
    [int]$ExpectedUnits = 675
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$runPath = if ([IO.Path]::IsPathRooted($Run)) { $Run } else { Join-Path $root $Run }
$stdoutPath = if ([IO.Path]::IsPathRooted($StdoutLog)) { $StdoutLog } else { Join-Path $root $StdoutLog }
$stderrPath = if ([IO.Path]::IsPathRooted($StderrLog)) { $StderrLog } else { Join-Path $root $StderrLog }
$output = Join-Path $root "$OutputRoot/$EventTimestamp-phase7-host-sleep-abort-diagnostic"

function Write-Utf8Lf {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Content
    )
    $normalized = $Content.Replace("`r`n", "`n").Replace("`r", "`n")
    if (-not $normalized.EndsWith("`n")) { $normalized += "`n" }
    [IO.File]::WriteAllText($Path, $normalized, [Text.UTF8Encoding]::new($false))
}

if (-not (Test-Path -LiteralPath $runPath -PathType Container)) {
    throw "campaign directory not found: $runPath"
}
foreach ($path in @($stdoutPath, $stderrPath)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "campaign log not found: $path"
    }
}
if (Test-Path -LiteralPath $output) {
    throw "refusing to overwrite diagnostic: $output"
}

$designPath = Join-Path $runPath "design-units.jsonl"
$unitRoot = Join-Path $runPath "units"
$designCount = @(Get-Content -LiteralPath $designPath).Count
$unitFiles = @(Get-ChildItem -LiteralPath $unitRoot -File -Filter "*.json" | Sort-Object Name)
$stdoutLines = @(Get-Content -LiteralPath $stdoutPath)
$lastProgress = @($stdoutLines | Where-Object { $_ -match '^\[\d+/\d+\]' } | Select-Object -Last 1)

$sleepStart = [datetime]"2026-08-31T15:16:45"
$sleepEnd = [datetime]"2026-08-31T15:17:15"
$events = @(
    Get-WinEvent -FilterHashtable @{
        LogName = "System"
        StartTime = $sleepStart
        EndTime = $sleepEnd
        Id = @(42, 107)
    } -ErrorAction Stop |
        Sort-Object TimeCreated |
        ForEach-Object {
            [ordered]@{
                time_created = $_.TimeCreated.ToUniversalTime().ToString("o")
                event_id = $_.Id
                provider = $_.ProviderName
                level = $_.LevelDisplayName
                message = $_.Message
                record_id = $_.RecordId
            }
        }
)
$sleepEvent = @($events | Where-Object { $_.event_id -eq 42 })
$resumeEvent = @($events | Where-Object { $_.event_id -eq 107 })
if ($sleepEvent.Count -ne 1 -or $resumeEvent.Count -ne 1) {
    throw "expected one sleep event and one resume event; found sleep=$($sleepEvent.Count), resume=$($resumeEvent.Count)"
}
if ($sleepEvent[0].message -notmatch "Sleep Reason: Application API") {
    throw "sleep event did not report Application API"
}

$processStillExists = $null -ne (Get-CimInstance Win32_Process -Filter "ProcessId=$CampaignPid")
$sourceFiles = @(Get-ChildItem -LiteralPath $runPath -File -Recurse | Sort-Object FullName)
$sourceIndex = @(
    foreach ($file in $sourceFiles) {
        [ordered]@{
            path = [IO.Path]::GetRelativePath($runPath, $file.FullName).Replace("\", "/")
            bytes = $file.Length
            last_write_utc = $file.LastWriteTimeUtc.ToString("o")
            sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    }
)

New-Item -ItemType Directory -Path $output | Out-Null
[IO.File]::WriteAllBytes((Join-Path $output "runner.stdout.log"), [IO.File]::ReadAllBytes($stdoutPath))
[IO.File]::WriteAllBytes((Join-Path $output "runner.stderr.log"), [IO.File]::ReadAllBytes($stderrPath))
Write-Utf8Lf (Join-Path $output "power-events.json") ($events | ConvertTo-Json -Depth 6)
Write-Utf8Lf (Join-Path $output "source-index.json") ($sourceIndex | ConvertTo-Json -Depth 5)

$diagnostic = [ordered]@{
    schema_version = 1
    event_id = "phase7-campaign-abort-2"
    captured_at = (Get-Date).ToUniversalTime().ToString("o")
    source_run = Split-Path -Leaf $runPath
    planned_unit_count = $ExpectedUnits
    design_unit_count = $designCount
    completed_trace_count = $unitFiles.Count
    last_progress_line = if ($lastProgress.Count -eq 1) { $lastProgress[0] } else { $null }
    campaign_pid = $CampaignPid
    campaign_process_present_at_capture = $processStillExists
    final_manifest_present = Test-Path -LiteralPath (Join-Path $runPath "manifest.json")
    summary_present = Test-Path -LiteralPath (Join-Path $runPath "summary.json")
    stderr_bytes = (Get-Item -LiteralPath $stderrPath).Length
    source_file_count = $sourceFiles.Count
    source_index_sha256 = (Get-FileHash -LiteralPath (Join-Path $output "source-index.json") -Algorithm SHA256).Hash.ToLowerInvariant()
    host_event = [ordered]@{
        observed = $true
        sleep_event_utc = $sleepEvent[0].time_created
        resume_event_utc = $resumeEvent[0].time_created
        sleep_reason = "Application API"
        event_log = "System"
        evidence_file = "power-events.json"
        interpretation = "The host entered an Application-API sleep transition within seconds of the last campaign write; the campaign process and Docker engine were absent after the host later resumed."
    }
    admissibility = [ordered]@{
        campaign_complete = $false
        dataset_release_eligible = $false
        outcome_analysis_eligible = $false
        partial_trace_reusable = $false
        resume_permitted = $false
        required_recovery = "Preserve this interrupted run and execute a new full preregistered campaign from unit 1 on a clean stack."
    }
    claim_boundaries = [ordered]@{
        evidence_type = "sandbox operational interruption"
        radio_access = "simulated"
        hardware = "not measured"
        operator_validation = "not performed"
        publication_result = "not evaluated"
    }
}
Write-Utf8Lf (Join-Path $output "diagnostic.json") ($diagnostic | ConvertTo-Json -Depth 8)

$captured = [ordered]@{}
Get-ChildItem -LiteralPath $output -File | Sort-Object Name | ForEach-Object {
    $captured[$_.Name] = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
}
$manifest = [ordered]@{
    schema_version = 1
    run_id = Split-Path -Leaf $output
    passed = $true
    scope = "read-only diagnosis of an inadmissible host-sleep-interrupted campaign"
    source_campaign_passed = $false
    outcome_analysis_performed = $false
    captured_file_sha256 = $captured
}
Write-Utf8Lf (Join-Path $output "manifest.json") ($manifest | ConvertTo-Json -Depth 6)

Write-Output "PASS: Phase 7 host-sleep abort diagnostic captured"
Write-Output "COMPLETED_TRACES=$($unitFiles.Count)"
Write-Output "EVIDENCE=$output"
