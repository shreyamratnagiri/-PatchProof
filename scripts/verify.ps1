# PowerShell 5.1+/7; runs each gate and returns nonzero on any failure.
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
New-Item -ItemType Directory -Path '.verification-logs' -Force | Out-Null
$log = Join-Path (Resolve-Path '.verification-logs').Path ("verification-{0}.txt" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
$failed = 0
function Invoke-Check {
  param([string]$Name,[string]$Executable,[string[]]$Arguments)
  Add-Content $log ("== {0} ==" -f $Name)
  try {
    & $Executable @Arguments *>> $log
    $code = $LASTEXITCODE
    if ($null -eq $code) {$code = 0}
  } catch {
    Add-Content $log $_.Exception.Message
    $code = 1
  }
  if ($code -eq 0) {Write-Host "PASS $Name"}
  else {Write-Host "FAIL $Name [exit $code]" -ForegroundColor Red; $script:failed++}
}
# Only named keys are accepted; never Invoke-Expression content from a .env file.
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
if (-not (Test-Path $python)) {
  Write-Host 'Missing .venv. First run: py -3.12 -m venv .venv; .\.venv\Scripts\python.exe -m pip install -e ".[dev]"' -ForegroundColor Yellow
  exit 1
}

# Forced disposable storage: never apply migrations to .env's application DB.
$verificationRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("patchproof-verify-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $verificationRoot -Force | Out-Null
$artifactRoot = Join-Path $verificationRoot 'artifacts'
New-Item -ItemType Directory -Path $artifactRoot -Force | Out-Null
$sqlitePath = (Join-Path $verificationRoot 'verification.db').Replace('\','/')
$env:PATCHPROOF_DATABASE_URL = "sqlite:///$sqlitePath"
$env:PATCHPROOF_DATA = $artifactRoot
# Do not run PostgreSQL integration tests against any inherited user test database.
Remove-Item Env:PATCHPROOF_TEST_DATABASE_URL -ErrorAction SilentlyContinue
Remove-Item Env:PATCHPROOF_REQUIRE_POSTGRES -ErrorAction SilentlyContinue
try {
Invoke-Check 'python-version' $python @('--version')
Invoke-Check 'python-dependencies' $python @('-m','pip','check')
Invoke-Check 'python-compilation' $python @('-m','compileall','-q','apps','packages','benchmarks','tests','scripts')
Invoke-Check 'python-tests' $python @('-m','pytest','-q')
Invoke-Check 'ruff-lint' $python @('-m','ruff','check','packages','apps/api','benchmarks','scripts','tests')
Invoke-Check 'ruff-format' $python @('-m','ruff','format','--check','packages','apps/api','benchmarks','scripts','tests')
Invoke-Check 'mypy' $python @('-m','mypy','packages','apps/api','--ignore-missing-imports')
Invoke-Check 'migration' $python @('-m','alembic','upgrade','head')
Invoke-Check 'benchmark' $python @('-m','benchmarks.evaluate','--output',(Join-Path $verificationRoot 'benchmark'))
Invoke-Check 'z3-inference' $python @('-c','from packages.properties import check_linear_int_property as p; assert p(["x"],[{"left":"x","op":">=","right":5}],{"left":"x","op":">=","right":0})["status"] == "proved"')
Invoke-Check 'tree-sitter-inference' $python @('-c','from packages.intelligence import _js_analysis; assert _js_analysis("function f(){return 1}","javascript")[2]')
Invoke-Check 'source-secret-scan' $python @('-m','scripts.security_scan')
Invoke-Check 'dependency-audit' $python @('-m','pip_audit','--progress-spinner','off')
Invoke-Check 'docker-compose-config' 'docker' @('compose','config','-q')
Invoke-Check 'docker-sandbox' $python @('-m','scripts.sandbox_smoke')
Invoke-Check 'ollama-inference' $python @('-m','scripts.model_smoke')
Invoke-Check 'real-repair-smoke' $python @('-m','scripts.repair_smoke')
Push-Location 'apps/web'
try {
  Invoke-Check 'npm-clean-install' 'npm.cmd' @('ci')
  Invoke-Check 'typescript-build' 'npm.cmd' @('run','build')
  Invoke-Check 'frontend-lint' 'npm.cmd' @('run','lint')
  Invoke-Check 'frontend-format' 'npm.cmd' @('run','format:check')
  Invoke-Check 'frontend-tests' 'npm.cmd' @('test')
  Invoke-Check 'playwright' 'npm.cmd' @('run','e2e')
} finally {Pop-Location}
Write-Host "TOTAL FAILED: $failed"
Write-Host "LOG: $log"
} finally {
  # This directory was created by this verification process and never points at
  # any persistent application data or user-supplied storage path.
  Remove-Item -LiteralPath $verificationRoot -Recurse -Force -ErrorAction SilentlyContinue
}
if ($failed -gt 0) {exit 1}
exit 0
