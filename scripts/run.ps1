$ErrorActionPreference = "Stop"

$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $projectRoot

$env:PYTHONPATH = Join-Path $projectRoot "src"
python -m uwo_helper

