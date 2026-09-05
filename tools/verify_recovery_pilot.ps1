param([string]$Run = '')
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo '.venv\Scripts\python.exe'
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$output = Join-Path $repo "evidence/verification/$stamp-recovery-pilot-r1"
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
    $lock = & $python -c "from tools.run_phase7_analysis import verify_analysis_lock; print(verify_analysis_lock()['lock_id'])" 2>&1
    if ($LASTEXITCODE -ne 0) { throw 'Frozen statistical source lock failed' }
    Save-Text 'analysis-lock.log' ($lock -join "`n")
    $auditPassed = $null
    if ($Run) {
        $audit = & $python tools/audit_recovery_pilot.py --run $Run 2>&1
        $auditPassed = $LASTEXITCODE -eq 0
        Save-Text 'independent-pilot-audit.json' ($audit -join "`n")
    }
    $sources = [ordered]@{}
    foreach ($file in @('sandbox/run_recovery_pilot.py','config/experiments/recovery-pilot-r1.json','docs/RECOVERY_PILOT_R1_PROTOCOL.md','tools/audit_recovery_pilot.py','tests/test_recovery_pilot.py','tools/verify_recovery_pilot.ps1')) {
        $normalized = [IO.File]::ReadAllText((Join-Path $repo $file)).Replace("`r`n", "`n").Replace("`r", "`n")
        $sha = [Security.Cryptography.SHA256]::Create()
        try { $sources[$file] = ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($normalized)))).Replace('-', '').ToLowerInvariant() }
        finally { $sha.Dispose() }
    }
    $report = [ordered]@{
        software_verification_passed = $true
        pilot_audit_passed = $auditPassed
        run = $Run
        source_sha256 = $sources
        source_hash_mode = 'utf8-lf-normalized'
        confirmatory_analysis_run = $false
        long_campaign_ready = $false
        TNSM_ready = $false
        live_actuation = $false
    }
    Save-Text 'verification.json' ($report | ConvertTo-Json -Depth 5)
    $hashes = [ordered]@{}
    Get-ChildItem -LiteralPath $output -File | Sort-Object Name | ForEach-Object {
        $hashes[$_.Name] = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    Save-Text 'manifest.json' (@{captured_file_sha256=$hashes} | ConvertTo-Json -Depth 5)
    Write-Output ($tests -join "`n")
    Write-Output "EVIDENCE=$output"
    if ($auditPassed -eq $false) { throw 'Pilot was not accepted; failed audit preserved' }
}
finally { Pop-Location }
