$ErrorActionPreference='Stop'
Set-Location (Join-Path $PSScriptRoot '..')
# Load only allowlisted literal .env assignments, never evaluate the file as code.
if (Test-Path '.env') {
  foreach ($line in Get-Content '.env') {
    if ($line -match '^([A-Za-z_][A-Za-z_0-9]*)=(.*)$') {
      if ($matches[1] -in @('PATCHPROOF_API_KEY','PATCHPROOF_DB_PASSWORD','PATCHPROOF_DATABASE_URL','PATCHPROOF_DATA','PATCHPROOF_OLLAMA_URL','PATCHPROOF_PATCH_MODEL','PATCHPROOF_EMBED_MODEL')) {
        [Environment]::SetEnvironmentVariable($matches[1],$matches[2],'Process')
      }
    }
  }
}
$python = Join-Path (Get-Location) '.venv/Scripts/python.exe'
if (-not (Test-Path $python)) { Write-Error 'Create .venv with Python 3.12 and install .[dev] first'; exit 2 }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Write-Error 'Docker Desktop CLI is missing'; exit 2 }
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) { Write-Error 'Ollama CLI is missing'; exit 2 }
& docker info *> $null
if ($LASTEXITCODE -ne 0) { Write-Error 'Docker daemon not available'; exit 2 }
# A dedicated disposable database/artifact path prevents test data from landing
# in a database configured for normal application operations.
$demoRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("patchproof-repair-demo-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $demoRoot -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $demoRoot 'artifacts') -Force | Out-Null
$sqlitePath = (Join-Path $demoRoot 'demo.db').Replace('\','/')
$env:PATCHPROOF_DATABASE_URL = "sqlite:///$sqlitePath"
$env:PATCHPROOF_DATA = (Join-Path $demoRoot 'artifacts')
try {
  & $python -m scripts.repair_smoke
  $result = $LASTEXITCODE
} finally {
  Remove-Item -LiteralPath $demoRoot -Recurse -Force -ErrorAction SilentlyContinue
}
exit $result
