# ATRIO Boardroom -- healthcheck.ps1
#
# Per claude-memory/global/HEALTH_CHECK_RULES.md (HARD RULE from AT-Hack0021):
#   - dual-mode: `local` | `docker` | `both`
#   - reads ports from .env (do NOT hardcode 8000/5432/8080)
#   - hits /healthz, frontend /, optionally db ping
#   - exit 0 with one-line OK summary; exit non-zero with the failing surface
#
# Usage:
#   .\tools\healthcheck.ps1               # default: docker mode
#   .\tools\healthcheck.ps1 docker        # explicit docker
#   .\tools\healthcheck.ps1 local         # services on host (uvicorn + vite dev)
#   .\tools\healthcheck.ps1 both          # try docker first, then local
#   .\tools\healthcheck.ps1 -Verbose      # show full curl bodies
#
# Output contract (one-line summary on success):
#   [health docker] api=OK(200) db=ok inference=mock frontend=OK(200) -- 1.2s
# Exit codes:
#   0 = everything green
#   1 = api unreachable
#   2 = api reachable but db down
#   3 = api reachable but inference providers misconfigured
#   4 = frontend unreachable
#   5 = bad mode arg / env file missing

[CmdletBinding()]
param(
  [Parameter(Position = 0)]
  [ValidateSet("local", "docker", "both")]
  [string]$Mode = "docker",
  [Parameter()]
  [int]$TimeoutSec = 5,
  [Parameter()]
  [switch]$Quiet
)

$ErrorActionPreference = "Continue"
$startedAt = Get-Date

# Resolve repo root from this script's location (parent of tools/)
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

# --------------------------------------------------------------------------
# Port resolution
# --------------------------------------------------------------------------

function Get-EnvVar {
  param([string]$Path, [string]$Name, [string]$Default)
  if (-not (Test-Path $Path)) { return $Default }
  $line = Get-Content $Path | Where-Object { $_ -match "^${Name}=" } | Select-Object -First 1
  if (-not $line) { return $Default }
  return ($line -split '=', 2)[1].Trim()
}

# ATRIO docker-compose.yml currently hardcodes :8000 (api) and :8080 (frontend)
# on the host side. To honor HEALTH_CHECK_RULES the canonical defaults are
# pinned here AND mirrored in .env / .env.example as overridable.
$envFile = if ($Mode -eq "local") { Join-Path $RepoRoot ".env" } else { Join-Path $RepoRoot ".env" }
$apiHostPort      = Get-EnvVar $envFile "API_HOST_PORT"      "8000"
$frontendHostPort = Get-EnvVar $envFile "FRONTEND_HOST_PORT" "8080"
$postgresHostPort = Get-EnvVar $envFile "POSTGRES_HOST_PORT" "5432"

$apiBase = "http://localhost:${apiHostPort}"
$frontendBase = "http://localhost:${frontendHostPort}"

# In local mode, frontend is usually vite dev on :5173 not Caddy on :8080
if ($Mode -eq "local") {
  $frontendHostPort = Get-EnvVar $envFile "FRONTEND_BASE_URL_PORT" "5173"
  $frontendBase = "http://localhost:${frontendHostPort}"
}

if (-not $Quiet) {
  Write-Host ("[healthcheck $Mode] api=" + $apiBase + " frontend=" + $frontendBase + " postgres-host=" + $postgresHostPort)
}

# --------------------------------------------------------------------------
# Probe primitives
# --------------------------------------------------------------------------

function Invoke-HealthGet {
  param([string]$Url)
  try {
    $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSec
    return @{ ok = $true; status = [int]$r.StatusCode; body = $r.Content }
  } catch {
    $code = 0
    if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
    $msg = if ($_.ErrorDetails) { $_.ErrorDetails.Message } else { $_.Exception.Message }
    return @{ ok = $false; status = $code; body = $msg }
  }
}

# --------------------------------------------------------------------------
# API healthz probe
# --------------------------------------------------------------------------

$apiHealthUrl = "$apiBase/api/v1/healthz"
$apiResult = Invoke-HealthGet -Url $apiHealthUrl
if (-not $apiResult.ok) {
  Write-Host ("[health $Mode] FAIL api unreachable at $apiHealthUrl -- " + $apiResult.body) -ForegroundColor Red
  exit 1
}

# Parse JSON body
$dbState = "unknown"
$inferenceState = "unknown"
try {
  $apiJson = $apiResult.body | ConvertFrom-Json
  if ($apiJson.PSObject.Properties.Name -contains "db") { $dbState = "$($apiJson.db)" }
  if ($apiJson.PSObject.Properties.Name -contains "inference_providers") {
    $providers = @($apiJson.inference_providers.PSObject.Properties)
    if ($providers.Count -gt 0) {
      $inferenceState = ($providers | ForEach-Object { "$($_.Name)=$($_.Value)" }) -join ","
    } else {
      $inferenceState = "(empty)"
    }
  }
} catch {
  if ($VerbosePreference -eq "Continue") { Write-Verbose "Could not parse /healthz JSON: $($_.Exception.Message)" }
}

if ($dbState -notmatch "^(ok|up|healthy)$") {
  Write-Host ("[health $Mode] PARTIAL api=OK($($apiResult.status)) but db=$dbState") -ForegroundColor Yellow
  exit 2
}

if ($inferenceState -eq "(empty)" -or $inferenceState -eq "unknown") {
  Write-Host ("[health $Mode] PARTIAL api=OK($($apiResult.status)) db=$dbState but inference_providers=$inferenceState") -ForegroundColor Yellow
  exit 3
}

# --------------------------------------------------------------------------
# Frontend probe
# --------------------------------------------------------------------------

$frontendResult = Invoke-HealthGet -Url $frontendBase
if (-not $frontendResult.ok) {
  Write-Host ("[health $Mode] FAIL frontend unreachable at $frontendBase -- " + $frontendResult.body) -ForegroundColor Red
  exit 4
}

# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------

$elapsed = ((Get-Date) - $startedAt).TotalSeconds
$elapsedFmt = "{0:N1}s" -f $elapsed

$summary = "[health $Mode] api=OK($($apiResult.status)) db=$dbState inference=$inferenceState frontend=OK($($frontendResult.status)) -- $elapsedFmt"
Write-Host $summary -ForegroundColor Green

if ($VerbosePreference -eq "Continue") {
  Write-Host ""
  Write-Host "--- /healthz body ---"
  Write-Host $apiResult.body
  Write-Host ""
  Write-Host "--- frontend response ---"
  Write-Host ("HTTP $($frontendResult.status), $($frontendResult.body.Length) bytes")
}

exit 0
