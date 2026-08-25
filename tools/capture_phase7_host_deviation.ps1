param(
    [string]$OutputRoot = "evidence/environment"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$output = Join-Path $root "$OutputRoot/$stamp-phase7-co-resident-containers"
New-Item -ItemType Directory -Path $output | Out-Null
$safeTwin = @(
    "safetwin5g-mongodb",
    "safetwin5g-open5gs",
    "safetwin5g-gnb",
    "safetwin5g-ue",
    "safetwin5g-prometheus"
)
$coResident = @(
    "nvg-access",
    "nvg-admin",
    "nvg-core",
    "nvg-dmz",
    "nvg-partner",
    "nvg-service"
)

Push-Location $root
try {
    docker stats --no-stream --format '{{json .}}' @coResident |
        Set-Content -LiteralPath (Join-Path $output "co-resident-stats.jsonl") -Encoding utf8
    if ($LASTEXITCODE -ne 0) { throw "co-resident docker stats failed" }

    $containers = @()
    foreach ($name in ($safeTwin + $coResident)) {
        $containers += docker inspect $name | ConvertFrom-Json
        if ($LASTEXITCODE -ne 0) { throw "docker inspect failed: $name" }
    }
    $inventory = foreach ($container in $containers) {
        [ordered]@{
            name = $container.Name.TrimStart("/")
            image = $container.Config.Image
            started_at = $container.State.StartedAt
            status = $container.State.Status
            networks = @($container.NetworkSettings.Networks.PSObject.Properties.Name | Sort-Object)
        }
    }
    $inventory | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $output "container-inventory.json") -Encoding utf8

    $processor = Get-CimInstance Win32_Processor | Select-Object Name, NumberOfCores, NumberOfLogicalProcessors, LoadPercentage
    $hostInfo = [ordered]@{
        captured_at = (Get-Date).ToUniversalTime().ToString("o")
        processor = @($processor)
        total_visible_memory_bytes = (Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory
    }
    $hostInfo | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $output "host-snapshot.json") -Encoding utf8

    $note = [ordered]@{
        schema_version = 1
        passed = $true
        scope = "mid-campaign co-resident-container observation"
        mutation_performed = $false
        containers_stopped_or_changed = $false
        safetwin_network = "safetwin5g-isolated"
        network_overlap_observed = $false
        shared_host_resource_isolation = $false
        interpretation = "Network namespaces are distinct, but CPU, memory, kernel, Docker engine, and host scheduling remain shared. A single idle stats snapshot does not prove absence of interference."
        required_limitation = "CPU-saturation and timing outcomes may be affected by uncontrolled shared-host contention from co-resident containers that appeared after campaign start."
        evidence_label = "sandbox-measured"
        radio_evidence_label = "simulated"
        hardware_evidence_label = $null
        operator_validation = $false
    }
    $note | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $output "deviation.json") -Encoding utf8

    $captured = @{}
    Get-ChildItem -LiteralPath $output -File | ForEach-Object {
        $captured[$_.Name] = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $manifest = [ordered]@{
        schema_version = 1
        run_id = Split-Path -Leaf $output
        passed = $true
        mutation_performed = $false
        captured_file_sha256 = $captured
    }
    $manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $output "manifest.json") -Encoding utf8
    Write-Output "PASS: read-only Phase 7 host-deviation snapshot captured"
    Write-Output "EVIDENCE=$output"
}
finally {
    Pop-Location
}
