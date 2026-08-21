# run_all.ps1 - doppio click da PowerShell, oppure:  .\run_all.ps1
# Se la chiave non e' gia' nell'ambiente, mettila qui sotto togliendo il #
# $env:ANTHROPIC_API_KEY = "sk-ant-..."

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

if (Test-Path ".\venv\Scripts\Activate.ps1") {
    . .\venv\Scripts\Activate.ps1
}

python run.py @args

if (Test-Path ".\web\index.html") {
    Write-Host ""
    Write-Host "Apro il sito nel browser..."
    Start-Process ".\web\index.html"
}
