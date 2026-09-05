param(
    [Parameter(Mandatory = $true)][string]$Run,
    [Parameter(Mandatory = $true)][string]$RuntimeEvidence
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$runPath = (Resolve-Path -LiteralPath (Join-Path $repo $Run)).Path
$runtimePath = (Resolve-Path -LiteralPath (Join-Path $repo $RuntimeEvidence)).Path
if (-not $runPath.StartsWith((Join-Path $repo 'evidence\scenarios\'), [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Run must be a campaign inside this repository'
}
if (-not $runtimePath.StartsWith((Join-Path $repo 'evidence\environment\'), [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Runtime evidence must be inside this repository'
}
$python = Join-Path $repo '.venv\Scripts\python.exe'
& (Join-Path $PSScriptRoot 'run_with_sleep_inhibition.ps1') `
    -FilePath $python `
    -ArgumentList @('sandbox/run_phase7.py', '--resume', $Run) `
    -WorkingDirectory $repo `
    -StdoutPath (Join-Path $runtimePath 'campaign.stdout.log') `
    -StderrPath (Join-Path $runtimePath 'campaign.stderr.log')
exit $LASTEXITCODE
