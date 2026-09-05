$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo '.venv\Scripts\python.exe'
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$output = Join-Path $repo "evidence/verification/$stamp-phase7-recovery-guard"
New-Item -ItemType Directory -Path $output | Out-Null

function Save-Text([string]$Name, [string]$Value) {
    $normalized = $Value.Replace("`r`n", "`n").Replace("`r", "`n")
    [IO.File]::WriteAllText((Join-Path $output $Name), $normalized + "`n", [Text.UTF8Encoding]::new($false))
}

Push-Location $repo
try {
    $tests = & $python -m pytest -q 2>&1
    $testExit = $LASTEXITCODE
    Save-Text 'full-tests.log' ($tests -join "`n")
    if ($testExit -ne 0) { throw 'Regression suite failed' }
    $audit = & $python tools/audit_phase7_run.py --run evidence/scenarios/20260901T030631Z-phase7-campaign-v2a --expected-units 675 --expected-blocks 135 2>&1
    $auditExit = $LASTEXITCODE
    $auditText = $audit -join "`n"
    Save-Text 'expected-campaign-rejection.log' $auditText
    if ($auditExit -eq 0 -or $auditText -notmatch 'user-plane (baseline|recovery) failed') {
        throw 'Corrected auditor did not reject the observed service outage'
    }
    $lock = & $python -c "from tools.run_phase7_analysis import verify_analysis_lock; print(verify_analysis_lock()['lock_id'])" 2>&1
    if ($LASTEXITCODE -ne 0) { throw 'Frozen analysis sources changed' }
    Save-Text 'analysis-lock.log' ($lock -join "`n")
    $prefix = & $python tools/audit_phase7_resume.py --checkpoint evidence/environment/20260905T015200Z-phase7-resume-checkpoint --run evidence/scenarios/20260901T030631Z-phase7-campaign-v2a 2>&1
    if ($LASTEXITCODE -ne 0) { throw 'Original checkpoint was modified' }
    Save-Text 'prefix-audit.json' ($prefix -join "`n")
    if (Test-Path -LiteralPath 'data/releases/safetwin5g-named-actions-v2a') {
        throw 'Rejected campaign unexpectedly has a release directory'
    }
    $sourceHashes = [ordered]@{}
    foreach ($file in @('src/safetwin5g/phase7_runner.py','sandbox/run_phase7.py','tools/audit_phase7_run.py','tools/diagnose_phase7_recovery.py','tools/verify_phase7_recovery_guard.ps1','tests/test_phase7_runner.py','docs/PHASE7_RECOVERY_REJECTION_1.md')) {
        $normalized = [IO.File]::ReadAllText((Join-Path $repo $file)).Replace("`r`n", "`n").Replace("`r", "`n")
        $sha = [Security.Cryptography.SHA256]::Create()
        try { $sourceHashes[$file] = ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($normalized)))).Replace('-', '').ToLowerInvariant() }
        finally { $sha.Dispose() }
    }
    $bundles = [ordered]@{}
    foreach ($bundle in @('evidence/decisions/20260905T040400Z-phase7-recovery-no-go','evidence/environment/20260905T015600Z-phase7-resume-runtime','evidence/verification/20260905T040100Z-phase7-campaign-dataset')) {
        $hashes = [ordered]@{}
        Get-ChildItem -LiteralPath (Join-Path $repo $bundle) -File | Sort-Object Name | ForEach-Object {
            $hashes[$_.Name] = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        }
        $bundles[$bundle] = $hashes
    }
    $report = [ordered]@{
        passed = $true
        scope = 'fail-closed recovery guard and faithful rejection of invalid campaign'
        campaign_acceptance = 'rejected'
        dataset_release_created = $false
        confirmatory_analysis_run = $false
        model_comparison_run = $false
        TNSM_manuscript_gate = 'no-go-data-quality'
        next_step = 'bounded repeated-interruption recovery engineering pilot before any new campaign'
        source_files_sha256 = $sourceHashes
        source_hash_mode = 'utf8-lf-normalized'
        preserved_bundle_files_sha256 = $bundles
        live_actuation = 'no-go'
        publication_submission_authorized = $false
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
