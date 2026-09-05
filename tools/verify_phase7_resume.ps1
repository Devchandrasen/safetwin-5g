param(
    [string]$Checkpoint = 'evidence/environment/20260905T015200Z-phase7-resume-checkpoint',
    [string]$Run = 'evidence/scenarios/20260901T030631Z-phase7-campaign-v2a'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo '.venv\Scripts\python.exe'
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$output = Join-Path $repo "evidence/verification/$stamp-phase7-resume"
New-Item -ItemType Directory -Path $output | Out-Null

function Save-Text([string]$Name, [string]$Value) {
    $normalized = $Value.Replace("`r`n", "`n").Replace("`r", "`n")
    [IO.File]::WriteAllText((Join-Path $output $Name), $normalized + "`n", [Text.UTF8Encoding]::new($false))
}

Push-Location $repo
try {
    $audit = & $python tools/audit_phase7_resume.py --checkpoint $Checkpoint --run $Run 2>&1
    $auditExit = $LASTEXITCODE
    Save-Text 'prefix-audit.json' ($audit -join "`n")
    if ($auditExit -ne 0) { throw 'Saved provenance audit failed' }
    $tests = & $python -m pytest -q 2>&1
    $testExit = $LASTEXITCODE
    Save-Text 'full-tests.log' ($tests -join "`n")
    if ($testExit -ne 0) { throw 'Regression suite failed' }
    $server = & docker version --format '{{json .Server}}' 2>&1
    if ($LASTEXITCODE -ne 0) { throw 'Docker version capture failed' }
    Save-Text 'docker-server.json' ($server -join "`n")
    $states = @()
    foreach ($name in @('safetwin5g-mongodb','safetwin5g-open5gs','safetwin5g-gnb','safetwin5g-ue','safetwin5g-prometheus')) {
        $inspection = & docker inspect --format '{{json .}}' $name
        if ($LASTEXITCODE -ne 0) { throw "Container inspection failed: $name" }
        $item = $inspection | ConvertFrom-Json
        $states += [ordered]@{
            name = $name
            image_id = $item.Image
            image_reference = $item.Config.Image
            started_at = $item.State.StartedAt
            status = $item.State.Status
            health = $item.State.Health.Status
            networks = @($item.NetworkSettings.Networks.PSObject.Properties.Name)
        }
    }
    Save-Text 'container-metadata.json' ($states | ConvertTo-Json -Depth 6)
    $checkpointHashes = [ordered]@{}
    Get-ChildItem -LiteralPath (Join-Path $repo $Checkpoint) -File | Sort-Object Name | ForEach-Object {
        $checkpointHashes[$_.Name] = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $sourceHashes = [ordered]@{}
    foreach ($file in @('tools/capture_phase7_resume.py','tools/audit_phase7_resume.py','tools/run_phase7_resume.ps1','tools/verify_phase7_resume.ps1','tests/test_phase7_resume.py','docs/PHASE7_PAUSE_RESUME_1.md')) {
        $normalized = [IO.File]::ReadAllText((Join-Path $repo $file)).Replace("`r`n", "`n").Replace("`r", "`n")
        $sha = [Security.Cryptography.SHA256]::Create()
        try { $sourceHashes[$file] = ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($normalized)))).Replace('-', '').ToLowerInvariant() }
        finally { $sha.Dispose() }
    }
    $report = [ordered]@{
        passed = $true
        scope = 'resume provenance, source verification, and regression suite'
        verified_at = (Get-Date).ToUniversalTime().ToString('o')
        checkpoint = $Checkpoint
        checkpoint_files_sha256 = $checkpointHashes
        source_files_sha256 = $sourceHashes
        source_files_hash_mode = 'utf8-lf-normalized'
        campaign_complete = $false
        campaign_acceptance_evaluated = $false
        outcomes_analyzed = $false
        next_step = 'complete 675 units and independent acceptance audits including P1 prefix preservation'
    }
    Save-Text 'verification.json' ($report | ConvertTo-Json -Depth 8)
    $captured = [ordered]@{}
    Get-ChildItem -LiteralPath $output -File | Sort-Object Name | ForEach-Object {
        $captured[$_.Name] = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    Save-Text 'manifest.json' (@{passed=$true; captured_file_sha256=$captured} | ConvertTo-Json -Depth 5)
    Write-Output ($tests -join "`n")
    Write-Output "EVIDENCE=$output"
}
finally { Pop-Location }
