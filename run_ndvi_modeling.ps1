# Run Rand's corrected NDVI model with explicit audited input and validation references.
# Usage (from any working directory):
#   powershell -ExecutionPolicy Bypass -File .\run_ndvi_modeling.ps1
param([string]$Python = "python")

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $Root
try {
    & $Python "scripts/ndvi_anomaly_detection.py" `
      --input "02_Field_Date_615/agrilens_real_field_date_QA_gated_615.csv" `
      --repo-root "." `
      --output-dir "output/ndvi_anomaly_v1" `
      --scene-qa "validation/results/date_scene_QA.csv" `
      --coordinate-reference "validation/results/field_geography.csv"
    if ($LASTEXITCODE -ne 0) {
        throw "NDVI modeling failed with exit code $LASTEXITCODE"
    }
} finally {
    Pop-Location
}
