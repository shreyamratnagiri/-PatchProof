#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../apps/web"
command -v npm >/dev/null || { echo 'Install Node.js 22/npm first' >&2; exit 1; }
npm install --package-lock-only --ignore-scripts --no-audit --no-fund
test -s package-lock.json || { echo 'npm did not generate a lockfile' >&2; exit 1; }
npm ci
npm run typecheck
npm run build
npm run lint
npm run format:check
npm run test
printf 'Frontend bootstrap succeeded; commit apps/web/package-lock.json.\n'
