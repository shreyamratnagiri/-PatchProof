$ErrorActionPreference='Stop'
Set-Location (Join-Path $PSScriptRoot '..')
$python = Join-Path (Get-Location) '.venv/Scripts/python.exe'
if (-not (Test-Path $python)) { Write-Error 'Install project dependencies into .venv first'; exit 2 }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Write-Error 'Docker Desktop CLI is missing'; exit 2 }
& docker info *> $null
if ($LASTEXITCODE -ne 0) { Write-Error 'Docker daemon not running'; exit 2 }
& docker build -f docker/pytest-runner.Dockerfile -t patchproof-pytest:3.12-9.0.2 .
if ($LASTEXITCODE -ne 0) { Write-Error 'Trusted pytest runner build failed'; exit $LASTEXITCODE }
& $python -m scripts.sandbox_smoke
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $python -m pytest -q tests/test_docker_integration.py -rs
exit $LASTEXITCODE
