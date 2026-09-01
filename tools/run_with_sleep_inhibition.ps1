param(
    [Parameter(Mandatory = $true)][string]$FilePath,
    [string[]]$ArgumentList = @(),
    [string]$WorkingDirectory = (Get-Location).Path,
    [string]$StdoutPath = "",
    [string]$StderrPath = "",
    [switch]$ProbeOnly
)

$ErrorActionPreference = "Stop"

if (-not ("SafeTwin5G.PowerState" -as [type])) {
    Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

namespace SafeTwin5G {
    public static class PowerState {
        [DllImport("kernel32.dll", SetLastError = true)]
        public static extern uint SetThreadExecutionState(uint esFlags);
    }
}
"@
}

$esContinuous = [uint32]2147483648
$esSystemRequired = [uint32]1
$requiredState = [uint32]($esContinuous -bor $esSystemRequired)
$previousState = [SafeTwin5G.PowerState]::SetThreadExecutionState($requiredState)
if ($previousState -eq 0) {
    throw "SetThreadExecutionState failed: $([Runtime.InteropServices.Marshal]::GetLastWin32Error())"
}

$childExitCode = 0
try {
    Write-Output "SLEEP_INHIBITION=ES_CONTINUOUS|ES_SYSTEM_REQUIRED"
    Write-Output "SLEEP_INHIBITION_PREVIOUS_STATE=$previousState"

    if ($ProbeOnly) {
        Write-Output "PROBE=PASS"
    }
    else {
        if (-not (Test-Path -LiteralPath $WorkingDirectory -PathType Container)) {
            throw "working directory not found: $WorkingDirectory"
        }

        $start = @{
            FilePath = $FilePath
            ArgumentList = $ArgumentList
            WorkingDirectory = $WorkingDirectory
            PassThru = $true
            NoNewWindow = $true
        }
        if ($StdoutPath) { $start.RedirectStandardOutput = $StdoutPath }
        if ($StderrPath) { $start.RedirectStandardError = $StderrPath }

        $child = Start-Process @start
        Write-Output "CHILD_PID=$($child.Id)"
        $child.WaitForExit()
        $childExitCode = $child.ExitCode
        Write-Output "CHILD_EXIT_CODE=$childExitCode"
    }
}
finally {
    $clearedState = [SafeTwin5G.PowerState]::SetThreadExecutionState($esContinuous)
    if ($clearedState -eq 0) {
        Write-Error "failed to clear SetThreadExecutionState: $([Runtime.InteropServices.Marshal]::GetLastWin32Error())"
    }
    else {
        Write-Output "SLEEP_INHIBITION_CLEARED=true"
    }
}

exit $childExitCode
