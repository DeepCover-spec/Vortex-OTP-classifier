# Windows equivalent of the Makefile. Usage:  .\run.ps1 train
# If scripts are blocked:  powershell -ExecutionPolicy Bypass -File run.ps1 train
param([Parameter(Position = 0)][string]$Target = "help")
$py = "python"
switch ($Target) {
    "data"    { & $py data/generate.py }
    "train"   { & $py src/train.py }
    "eval"    { & $py src/evaluate.py }
    "up"      { docker compose up --build }
    "demo"    { & $py scripts/run_shift_demo.py }
    "retrain" { & $py src/retrain.py }
    default   { Write-Host "Usage: .\run.ps1 data|train|eval|up|demo|retrain" }
}
