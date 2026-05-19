# ATRIO Demo Video — verification-b · run script
#
# Pipeline: pre-flight -> extract frames -> OCR + rubric grade -> JSON report

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent (Split-Path -Parent $here)
$resultsDir = Join-Path $projectRoot 'demovideo\results\creation'
$reportsDir = Join-Path $here 'reports'
$framesDir = Join-Path $here 'frames'
New-Item -Path $reportsDir -ItemType Directory -Force | Out-Null

$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$reportFile = Join-Path $reportsDir "vision-review-$stamp.json"

Write-Host ''
Write-Host '[verify-b] === Vision review (OCR + rubric) ===' -ForegroundColor Yellow

# 1) Locate the latest recorded video
$pointer = Join-Path $resultsDir 'latest.txt'
if (-not (Test-Path $pointer)) {
    Write-Host '[verify-b] no latest recording pointer found - run creation/ first' -ForegroundColor Red
    exit 1
}
$videoPath = (Get-Content $pointer -Raw).Trim()
if (-not (Test-Path $videoPath)) {
    Write-Host "[verify-b] pointer references missing video: $videoPath" -ForegroundColor Red
    exit 1
}
Write-Host "[verify-b] grading: $videoPath" -ForegroundColor Cyan

# 2) Verify ffmpeg + tesseract are available
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Host '[verify-b] ffmpeg not on PATH - install with: winget install Gyan.FFmpeg' -ForegroundColor Red
    exit 1
}
if (-not (Get-Command tesseract -ErrorAction SilentlyContinue)) {
    Write-Host '[verify-b] tesseract not on PATH - install with: winget install UB-Mannheim.TesseractOCR' -ForegroundColor Red
    exit 1
}

# 3) Extract frames (1 per 2s -> ~120-150 frames for 4-5 min video)
if (Test-Path $framesDir) { Remove-Item -Recurse -Force $framesDir }
Write-Host '[verify-b] extracting frames (1 per 2s) via ffmpeg' -ForegroundColor Cyan
python (Join-Path $here 'extract-frames.py') --video $videoPath --out $framesDir --every 2
if ($LASTEXITCODE -ne 0) {
    Write-Host '[verify-b] extract-frames failed' -ForegroundColor Red
    exit $LASTEXITCODE
}

# 4) OCR + grade against rubric
Write-Host '[verify-b] OCR + rubric grade' -ForegroundColor Cyan
python (Join-Path $here 'grade-frames.py') --frames $framesDir --report $reportFile
$gradeExit = $LASTEXITCODE

Write-Host ''
Write-Host "[verify-b] report : $reportFile"
if ($gradeExit -eq 0) {
    Write-Host '[verify-b] all rubric items PASS' -ForegroundColor Green
} else {
    Write-Host '[verify-b] some rubric items FAILED - review report' -ForegroundColor Yellow
}
exit $gradeExit
