param(
    [Parameter(Position = 0)]
    [ValidateSet("build", "up", "down", "status", "logs", "baseline", "capture-stack", "capture-baseline", "intervention")]
    [string] $Command = "status"
)

$sandboxRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$composeFile = Join-Path $sandboxRoot "compose.yaml"
$compose = @("compose", "-f", $composeFile)

function Invoke-DockerCompose {
    param([string[]] $Arguments)
    & docker @compose @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose failed with exit code $LASTEXITCODE"
    }
}

switch ($Command) {
    "build" {
        Invoke-DockerCompose @("build")
    }
    "up" {
        Invoke-DockerCompose @("up", "-d", "--wait", "--wait-timeout", "240")
    }
    "down" {
        Invoke-DockerCompose @("down")
    }
    "status" {
        Invoke-DockerCompose @("ps")
    }
    "logs" {
        Invoke-DockerCompose @("logs", "--no-color", "--tail", "200")
    }
    "capture-stack" {
        & python (Join-Path $sandboxRoot "capture_evidence.py") --stage stack
        if ($LASTEXITCODE -ne 0) { throw "stack evidence capture failed" }
    }
    "capture-baseline" {
        & python (Join-Path $sandboxRoot "capture_evidence.py") --stage baseline
        if ($LASTEXITCODE -ne 0) { throw "baseline evidence capture failed" }
    }
    "intervention" {
        & python (Join-Path $sandboxRoot "run_intervention.py")
        if ($LASTEXITCODE -ne 0) { throw "sandbox intervention failed" }
    }
    "baseline" {
        & docker exec safetwin5g-ue ip -brief address show uesimtun0
        if ($LASTEXITCODE -ne 0) { throw "UE PDU interface is missing" }
        & docker exec safetwin5g-ue ping -I uesimtun0 -c 5 -W 2 10.45.0.1
        if ($LASTEXITCODE -ne 0) { throw "PDU-session user-plane ping failed" }
        $targetJson = & docker exec safetwin5g-open5gs curl --fail --silent http://10.53.0.6:9090/api/v1/targets
        if ($LASTEXITCODE -ne 0) { throw "Prometheus target query failed inside the isolated network" }
        $targets = $targetJson | ConvertFrom-Json
        $unhealthy = @($targets.data.activeTargets | Where-Object health -ne "up")
        if ($unhealthy.Count -gt 0) { throw "One or more Prometheus targets are unhealthy" }
        $targets.data.activeTargets |
            Select-Object @{Name="job";Expression={$_.labels.job}}, health, scrapeUrl |
            Format-Table -AutoSize
    }
}
