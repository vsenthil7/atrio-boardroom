# ATRIO Demo Video Creation pipeline
# Builds the full 4-minute walkthrough video using the ISOLATED Playwright runner.
#
# Steps:
#   1. Pre-flight: docker compose stack up?
#   2. RESET: seed demo tenant (founder + ceo + mandate) to clean state
#   3. Run Playwright captioned full-walkthrough spec
#   4. Trim leading frame + transcode to mp4 + archive both webm + mp4
#
# Note: ffmpeg writes its banner to stderr, which trips $ErrorActionPreference='Stop'
# even on successful runs. We wrap ffmpeg calls in try/catch and check the
# OUTPUT FILE for success rather than the exit signal of the cmdlet.

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent (Split-Path -Parent $here)
$demoDir = Join-Path $projectRoot 'demo'
$backupDir = Join-Path $demoDir '_backup'
$resultsDir = Join-Path (Split-Path -Parent $here) 'results\creation'
$runnerDir = Join-Path $projectRoot 'demovideo\.runner'

Write-Host ''
Write-Host '[creation] === ATRIO Demo Video Creation ===' -ForegroundColor Yellow

# 1) Pre-flight
Write-Host '[creation] 1/4 pre-flight: docker compose stack up?' -ForegroundColor Cyan
$apiStatus = docker ps --filter 'name=atrio-api-1' --format '{{.Names}}:{{.Status}}' 2>$null
$feStatus = docker ps --filter 'name=atrio-frontend-1' --format '{{.Names}}:{{.Status}}' 2>$null
$pgStatus = docker ps --filter 'name=atrio-postgres-1' --format '{{.Names}}:{{.Status}}' 2>$null
if (-not ($apiStatus -match 'Up') -or -not ($feStatus -match 'Up') -or -not ($pgStatus -match 'Up')) {
    Write-Host '  stack not fully up - running docker compose up -d' -ForegroundColor Yellow
    Push-Location $projectRoot
    try {
        docker compose -f docker/docker-compose.yml --env-file .env up -d
        Start-Sleep -Seconds 12
    } finally { Pop-Location }
} else {
    Write-Host "  api      : $apiStatus"
    Write-Host "  frontend : $feStatus"
    Write-Host "  postgres : $pgStatus"
}

# Healthcheck before recording
$hc = & (Join-Path $projectRoot 'tools\healthcheck.ps1') docker 2>&1
Write-Host "  $hc"
if ($hc -match 'FAIL') {
    Write-Host '[creation] healthcheck FAILED - aborting' -ForegroundColor Red
    exit 1
}

# 2) RESET — seed demo tenant for a clean recording
Write-Host '[creation] 2/4 reset: seeding demo tenant via /api/v1/_test/seed-demo' -ForegroundColor Cyan
try {
    $seedResp = Invoke-WebRequest -Uri 'http://localhost:8000/api/v1/_test/seed-demo' -Method POST -UseBasicParsing -TimeoutSec 10
    if ($seedResp.StatusCode -eq 200) {
        $body = $seedResp.Content | ConvertFrom-Json
        Write-Host "  ok: tenant=$($body.tenant_id)  founder=$($body.founder_email)  ceo=$($body.second_email)"
    } else {
        Write-Host "[creation] seed returned $($seedResp.StatusCode) - aborting" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "[creation] seed POST failed: $_" -ForegroundColor Red
    exit 1
}

# 3) Run playwright spec using ISOLATED runner
Write-Host '[creation] 3/4 running playwright full-walkthrough spec (isolated runner)' -ForegroundColor Cyan
$pwBin = Join-Path $runnerDir 'node_modules\.bin\playwright.cmd'
if (-not (Test-Path $pwBin)) {
    Write-Host "[creation] isolated runner not installed at $runnerDir" -ForegroundColor Red
    Write-Host '          first time? run:' -ForegroundColor Yellow
    Write-Host "          cd $runnerDir" -ForegroundColor Yellow
    Write-Host '          npm install' -ForegroundColor Yellow
    Write-Host '          .\node_modules\.bin\playwright.cmd install chromium' -ForegroundColor Yellow
    exit 1
}
Push-Location $runnerDir
try {
    $env:WEB_BASE_URL = if ($env:WEB_BASE_URL) { $env:WEB_BASE_URL } else { 'http://localhost:8080' }
    $env:API_BASE_URL = if ($env:API_BASE_URL) { $env:API_BASE_URL } else { 'http://localhost:8000' }
    & $pwBin test --config=playwright.demo.config.ts --reporter=line
    if ($LASTEXITCODE -ne 0) {
        Write-Host '[creation] playwright spec failed - aborting archive' -ForegroundColor Red
        exit $LASTEXITCODE
    }
} finally {
    Pop-Location
}

# 4) Locate + archive video(s) — there are TWO recordings (founder + ceo contexts)
Write-Host '[creation] 4/4 locating + archiving recorded video' -ForegroundColor Cyan
New-Item -Path $demoDir -ItemType Directory -Force | Out-Null
New-Item -Path $backupDir -ItemType Directory -Force | Out-Null
New-Item -Path $resultsDir -ItemType Directory -Force | Out-Null

$testResultsDir = Join-Path $runnerDir 'test-results-demo'
$videos = Get-ChildItem $testResultsDir -Recurse -Filter '*.webm' -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending
if (-not $videos) {
    Write-Host "[creation] no recorded videos found in $testResultsDir" -ForegroundColor Red
    exit 1
}

Write-Host "  Found $($videos.Count) recordings (founder + ceo contexts):"
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$archived = @()
$i = 0
foreach ($v in $videos) {
    $i++
    $tag = if ($i -eq 1) { 'main' } else { "secondary-$i" }
    $dstName = "atrio-walkthrough-$stamp-$tag.webm"
    $dstMain = Join-Path $demoDir $dstName
    $dstBackup = Join-Path $backupDir $dstName

    $previousEAP = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
            & ffmpeg -y -ss 0.5 -i $v.FullName -c:v libvpx -b:v 1.2M -crf 10 -an $dstMain *> $null
            if (-not (Test-Path $dstMain) -or (Get-Item $dstMain).Length -le 1KB) {
                Copy-Item $v.FullName $dstMain -Force
            }
        } else {
            Copy-Item $v.FullName $dstMain -Force
        }
        Copy-Item $dstMain $dstBackup -Force
        $sz = [math]::Round((Get-Item $dstMain).Length / 1MB, 2)
        Write-Host "    [$tag] $dstName  ($sz MB)"

        # MP4 transcode for lablab.ai upload (mp4 mandatory)
        if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
            $mp4Dst = [System.IO.Path]::ChangeExtension($dstMain, '.mp4')
            & ffmpeg -y -i $dstMain -c:v libx264 -crf 22 -preset slow -an $mp4Dst *> $null
            if ((Test-Path $mp4Dst) -and ((Get-Item $mp4Dst).Length -gt 1KB)) {
                $mp4Sz = [math]::Round((Get-Item $mp4Dst).Length / 1MB, 2)
                Write-Host "    [$tag] $([System.IO.Path]::GetFileName($mp4Dst))  ($mp4Sz MB)"
                $archived += $mp4Dst
            }
        }
        $archived += $dstMain
    } finally {
        $ErrorActionPreference = $previousEAP
    }
}

# Pointer
if ($archived.Count -gt 0) {
    Set-Content -Path (Join-Path $resultsDir 'latest.txt') -Value $archived[0] -Encoding ASCII
}

Write-Host ''
Write-Host '[creation] done' -ForegroundColor Green
Write-Host "  archived $($archived.Count) files in $demoDir"
Write-Host "  pointer  : $(Join-Path $resultsDir 'latest.txt')"
