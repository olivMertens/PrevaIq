<#
.SYNOPSIS
    Runs a real Aurora forecast smoke test through a deployed PrevaIQ API.

.DESCRIPTION
    Verifies Aurora readiness, selects an existing property-claims dossier when
    -ApplicationId is omitted, submits a short forecast, and confirms that the
    completed result was persisted.

    Set PREVAIQ_API_KEY in the environment rather than passing -ApiKey on a
    shared shell command line.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ApiBaseUrl,

    [string]$ApiKey = $env:PREVAIQ_API_KEY,

    [string]$ApplicationId = "",

    [ValidateRange(-90, 90)]
    [double]$Latitude = 46.2044,

    [ValidateRange(-180, 180)]
    [double]$Longitude = 6.1432,

    [ValidateRange(1, 240)]
    [int]$HorizonHours = 6,

    [switch]$Ensemble
)

$ErrorActionPreference = "Stop"
$baseUrl = $ApiBaseUrl.TrimEnd("/")
if (-not $ApiKey) {
    throw "Set PREVAIQ_API_KEY or pass -ApiKey."
}
if ($HorizonHours % 6 -ne 0) {
    throw "HorizonHours must be a multiple of 6."
}

$headers = @{ "X-API-Key" = $ApiKey }
$status = Invoke-RestMethod -Method Get -Uri "$baseUrl/api/aurora/status" -Headers $headers
if (-not $status.enabled -or -not $status.configured) {
    $missing = @($status.missing) -join ", "
    throw "Aurora is not ready. Missing configuration: $missing"
}

if (-not $ApplicationId) {
    $response = Invoke-RestMethod -Method Get `
        -Uri "$baseUrl/api/applications?persona=property_casualty_claims" `
        -Headers $headers
    $applications = if ($response.items) { @($response.items) } else { @($response) }
    $ApplicationId = $applications |
        Where-Object { $_.id } |
        Select-Object -First 1 -ExpandProperty id
    if (-not $ApplicationId) {
        throw "No property-claims dossier exists. Restore a property demo case in the UI first."
    }
}

$payload = @{
    latitude = $Latitude
    longitude = $Longitude
    horizon_hours = $HorizonHours
    ensemble = [bool]$Ensemble
} | ConvertTo-Json

Write-Host "Submitting Aurora forecast for dossier $ApplicationId..." -ForegroundColor Cyan
$forecast = Invoke-RestMethod -Method Post `
    -Uri "$baseUrl/api/applications/$([uri]::EscapeDataString($ApplicationId))/aurora-forecast" `
    -Headers $headers `
    -ContentType "application/json" `
    -Body $payload `
    -TimeoutSec 960

if ($forecast.status -ne "completed" -or -not $forecast.result.task_id) {
    throw "Aurora did not return a completed task."
}
if (@($forecast.result.forecast.series).Count -lt 1) {
    throw "Aurora returned no forecast series."
}
if (-not $forecast.result.decision_support.severity -or
    -not $forecast.result.decision_support.human_review_required) {
    throw "Aurora returned no bounded decision-support assessment."
}

$persisted = Invoke-RestMethod -Method Get `
    -Uri "$baseUrl/api/applications/$([uri]::EscapeDataString($ApplicationId))/aurora-forecast" `
    -Headers $headers
if ($persisted.result.task_id -ne $forecast.result.task_id) {
    throw "The persisted Aurora task does not match the submitted task."
}

[pscustomobject]@{
    application_id = $ApplicationId
    task_id = $forecast.result.task_id
    model = $forecast.result.model
    horizon_hours = $forecast.result.horizon_hours
    forecast_points = @($forecast.result.forecast.series).Count
    max_wind_gust_ms = $forecast.result.forecast.max_wind_gust_ms
    total_precipitation_mm = $forecast.result.forecast.total_precipitation_mm
    weather_severity = $forecast.result.decision_support.severity
    triage_priority = $forecast.result.decision_support.triage_priority
    recommended_actions = @($forecast.result.decision_support.recommended_actions) -join ", "
    human_review_required = $forecast.human_review_required
} | Format-List
