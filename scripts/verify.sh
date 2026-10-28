#!/usr/bin/env bash
# Runs release checks rather than assuming dependencies exist. Exit 1 on any failed gate.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
repository_root="$(pwd)"
mkdir -p .verification-logs
report="$(pwd)/.verification-logs/verification-$(date +%Y%m%d-%H%M%S).txt"
failed=0
run() {
  local label="$1"; shift
  echo "== $label ==" | tee -a "$report"
  if "$@" >>"$report" 2>&1; then echo "PASS $label" | tee -a "$report"
  else code=$?; echo "FAIL $label [exit $code]" | tee -a "$report"; failed=$((failed+1)); fi
}
if [[ -f .env ]]; then
  # Source only explicitly named configuration entries, without evaluating shell.
  while IFS='=' read -r key value; do
    case "$key" in
      PATCHPROOF_API_KEY|PATCHPROOF_DB_PASSWORD|PATCHPROOF_DATABASE_URL|PATCHPROOF_DATA|PATCHPROOF_OLLAMA_URL|PATCHPROOF_PATCH_MODEL|PATCHPROOF_EMBED_MODEL)
        export "$key=$value" ;;
    esac
  done <.env
fi
# Never migrate or write to an application or production database during
# automated verification. All migration and smoke operations use a fresh SQLite
# database and artifact directory owned by this invocation.
verification_root="$(mktemp -d "${TMPDIR:-/tmp}/patchproof-verify.XXXXXXXX")" || exit 1
chmod 700 "$verification_root"
cleanup_verification() { rm -rf -- "$verification_root"; }
trap cleanup_verification EXIT
mkdir -p "$verification_root/artifacts"
export PATCHPROOF_DATABASE_URL="sqlite:///$verification_root/verification.db"
export PATCHPROOF_DATA="$verification_root/artifacts"
# Never allow inherited PostgreSQL integration URLs to make this disposable check destructive.
unset PATCHPROOF_TEST_DATABASE_URL PATCHPROOF_REQUIRE_POSTGRES
# For PostgreSQL integration, users must separately configure a dedicated *_test
# database. These tests refuse to operate on a non-test database.
python_bin="${PATCHPROOF_PYTHON:-python3}"
run "python-version" "$python_bin" --version
run "python-dependencies" "$python_bin" -m pip check
run "python-compilation" "$python_bin" -m compileall -q apps packages benchmarks tests scripts
run "python-tests" "$python_bin" -m pytest -q
run "ruff-lint" "$python_bin" -m ruff check packages apps/api benchmarks scripts tests
run "ruff-format" "$python_bin" -m ruff format --check packages apps/api benchmarks scripts tests
run "mypy" "$python_bin" -m mypy packages apps/api --ignore-missing-imports
run "migration" "$python_bin" -m alembic upgrade head
run "benchmark" "$python_bin" -m benchmarks.evaluate --output "$verification_root/benchmark"
run "z3-inference" "$python_bin" -c 'from packages.properties import check_linear_int_property as p; assert p(["x"],[{"left":"x","op":">=","right":5}],{"left":"x","op":">=","right":0})["status"] == "proved"'
run "tree-sitter-inference" "$python_bin" -c 'from packages.intelligence import _js_analysis; assert _js_analysis("function f(){return 1}","javascript")[2]'
run "source-secret-scan" "$python_bin" -m scripts.security_scan
run "dependency-audit" "$python_bin" -m pip_audit --progress-spinner off
run "docker-compose-config" docker compose config -q
run "docker-sandbox" "$python_bin" -m scripts.sandbox_smoke
run "ollama-inference" "$python_bin" -m scripts.model_smoke
run "real-repair-smoke" "$python_bin" -m scripts.repair_smoke
cd apps/web || exit 1
run "npm-clean-install" npm ci
run "typescript-build" npm run build
run "frontend-lint" npm run lint
run "frontend-format" npm run format:check
run "frontend-tests" npm test
run "playwright" npm run e2e
cd "$repository_root" || exit 1
echo "TOTAL FAILED: $failed" | tee -a "$report"
echo "RESULT LOG: $report"
[[ "$failed" -eq 0 ]]
