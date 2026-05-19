# ATRIO Demo Video — verification-a · run script

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent (Split-Path -Parent $here)
$runnerDir = Join-Path $projectRoot 'demovideo\.runner'
$reportsDir = Join-Path $here 'reports'
New-Item -Path $reportsDir -ItemType Directory -Force | Out-Null

$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$reportFile = Join-Path $reportsDir "structural-review-$stamp.txt"

Write-Host ''
Write-Host '[verify-a] === Structural review (24 hard assertions) ===' -ForegroundColor Yellow

# Pre-flight
Write-Host '[verify-a] pre-flight: docker stack' -ForegroundColor Cyan
$apiStatus = docker ps --filter 'name=atrio-api-1' --format '{{.Names}}:{{.Status}}' 2>$null
if (-not ($apiStatus -match 'Up')) {
    Write-Host '[verify-a] api not up - aborting' -ForegroundColor Red
    exit 1
}
Write-Host "  api: $apiStatus"

# Healthcheck
$hc = & (Join-Path $projectRoot 'tools\healthcheck.ps1') docker 2>&1
Write-Host "  $hc"
if ($hc -match 'FAIL') {
    Write-Host '[verify-a] healthcheck FAILED - aborting' -ForegroundColor Red
    exit 1
}

# Copy spec into the isolated runner specs/ so it can find caption-overlay etc.
$specSrc = Join-Path $here 'structural-review.spec.ts'
$specDst = Join-Path $runnerDir 'specs\structural-review.spec.ts'
Copy-Item $specSrc $specDst -Force

# Run via isolated runner
$pwBin = Join-Path $runnerDir 'node_modules\.bin\playwright.cmd'
if (-not (Test-Path $pwBin)) {
    Write-Host "[verify-a] isolated runner not installed at $runnerDir" -ForegroundColor Red
    exit 1
}

Push-Location $runnerDir
try {
    $env:API_BASE_URL = if ($env:API_BASE_URL) { $env:API_BASE_URL } else { 'http://localhost:8000' }
    & $pwBin test specs/structural-review.spec.ts --config=playwright.demo.config.ts --reporter=line 2>&1 | Tee-Object -FilePath $reportFile
    $exitCode = $LASTEXITCODE
} finally {
    Pop-Location
}

Write-Host ''
Write-Host "[verify-a] report: $reportFile" -ForegroundColor Green
exit $exitCode
