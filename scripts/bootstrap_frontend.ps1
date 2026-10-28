# Generate the real npm dependency lockfile and verify clean installation.
# This script never constructs integrity hashes itself.
$ErrorActionPreference = 'Stop'
Push-Location (Join-Path $PSScriptRoot '..\apps\web')
try {
  # Windows PowerShell may block npm.ps1 under the default execution policy.
  # npm.cmd is the official Node.js shim and does not require weakening it.
  $npm = if (Get-Command npm.cmd -ErrorAction SilentlyContinue) { 'npm.cmd' } else { 'npm' }
  if (-not (Get-Command $npm -ErrorAction SilentlyContinue)) { throw 'Node.js/npm is missing. Install Node.js 22 LTS.' }
  & $npm install --package-lock-only --ignore-scripts --no-audit --no-fund
  if ($LASTEXITCODE -ne 0) { throw 'npm registry could not provide dependency metadata. Lockfile was not generated.' }
  if (-not (Test-Path 'package-lock.json')) { throw 'npm did not create package-lock.json.' }
  & $npm ci
  if ($LASTEXITCODE -ne 0) { throw 'npm ci failed. Do not commit a broken lockfile.' }
  & $npm run typecheck
  if ($LASTEXITCODE -ne 0) { throw 'Strict TypeScript validation failed.' }
  & $npm run build
  if ($LASTEXITCODE -ne 0) { throw 'Vite build failed.' }
  & $npm run lint
  if ($LASTEXITCODE -ne 0) { throw 'ESLint failed.' }
  & $npm run format:check
  if ($LASTEXITCODE -ne 0) { throw 'Prettier failed. Apply the formatter before release.' }
  & $npm run test
  if ($LASTEXITCODE -ne 0) { throw 'Vitest failed.' }
  Write-Host 'Frontend bootstrap succeeded. Commit apps/web/package-lock.json.'
} finally { Pop-Location }
