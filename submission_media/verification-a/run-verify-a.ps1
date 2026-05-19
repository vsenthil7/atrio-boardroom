# ATRIO Pitch Deck — verification-a · run script
#
# Runs structural-review.py against the most recent atrio-pitch-deck-*.pdf.

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$submission = Split-Path -Parent $here

Write-Host ''
Write-Host '[verify-a] === ATRIO Pitch Deck · Structural review ===' -ForegroundColor Yellow

# 1) PyMuPDF check
Write-Host '[verify-a] pre-flight: PyMuPDF' -ForegroundColor Cyan
$pyExe = if (Test-Path 'C:\Users\v_sen\AppData\Local\Programs\Python\Python312\python.exe') {
    'C:\Users\v_sen\AppData\Local\Programs\Python\Python312\python.exe'
} else {
    (Get-Command python).Source
}
$check = & $pyExe -c "import fitz; print(fitz.__doc__.split(chr(10))[0])" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host '[verify-a] PyMuPDF not installed - installing now' -ForegroundColor Yellow
    & $pyExe -m pip install --quiet PyMuPDF
}
Write-Host "  python: $pyExe"

# 2) Locate the latest pdf
$pdf = Get-ChildItem $submission -Filter 'atrio-pitch-deck-*.pdf' -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if (-not $pdf) {
    Write-Host "[verify-a] no atrio-pitch-deck-*.pdf in $submission" -ForegroundColor Red
    Write-Host '  Build first: python atrio/scripts/build_pitch_deck.py && pwsh atrio/scripts/pptx_to_pdf.ps1' -ForegroundColor Yellow
    exit 1
}
Write-Host "[verify-a] grading: $($pdf.Name) ($([math]::Round($pdf.Length / 1KB, 1)) KB)" -ForegroundColor Cyan

# 3) Run structural review
& $pyExe (Join-Path $here 'structural-review.py')
$exitCode = $LASTEXITCODE
exit $exitCode
