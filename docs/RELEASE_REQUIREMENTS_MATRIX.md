# Last source-pass requirements matrix

Statuses describe **only the supporting evidence**, not a universal production guarantee. Commands shown were actually executed unless explicitly labeled "local-only".

| Requirement | Implementation file(s) | Test / command | Status | Remaining limitation |
| --- | --- | --- | --- | --- |
| Safe repository upload, persisted issues and repairs | `packages/ingest.py`, `apps/api/main.py` | `pytest -q tests/test_api_workflow.py tests/test_new_boundaries.py` | VERIFIED PASS | Larger real-world repositories untested |
| Consistent API create/retrieve schema and UTC dates | `apps/api/main.py` | `pytest -q tests/test_api_workflow.py` | VERIFIED PASS | PostgreSQL timezone semantics need runtime exercise |
| Python AST, lexical localization, graph calculations | `packages/intelligence.py`, `packages/retrieval.py` | `pytest -q tests/test_analysis_new.py`; `python -m benchmarks.evaluate --output ...` | VERIFIED PASS | Small fixture corpus; not external validation |
| Neural semantic retrieval and Ollama patch generation | `packages/retrieval.py`, `packages/repair.py` | `pytest -q tests/test_semantic_validation.py`; real `scripts/model_smoke.py` local-only | IMPLEMENTED BUT UNVERIFIED | Actual model inference unavailable |
| Pytest/unittest framework selection, empty suite, error classification | `packages/verification.py` | `pytest -q tests/test_pytest_sandbox_contract.py` | VERIFIED PASS | Pure contract tests, not actual Docker runtime |
| Trusted worker stages bounded copies and renews owned leases | `packages/sandbox_worker.py`, `packages/verification_jobs.py` | `pytest -q tests/test_worker_queue.py` | VERIFIED PASS | SQLite simulation, real worker runtime unverified |
| Container sandbox isolation and cleanup | `packages/verification.py`, `docker/pytest-runner.Dockerfile` | `pytest -q tests/test_docker_integration.py` | IMPLEMENTED BUT UNVERIFIED | 8 tests skipped: Docker unavailable |
| Unsupported JS/TSX test execution | `packages/verification.py` | Pure source and contract tests | NOT IMPLEMENTED | Explicitly unsupported; no universal test guarantee |
| Protected patch approval, export, report and cancellation | `apps/api/main.py`, `packages/verification_jobs.py` | `pytest -q tests/test_api_workflow.py tests/test_release_features.py tests/test_worker_queue.py` | VERIFIED PASS | Live browser + worker must still be tested |
| Z3 bounded integer checking | `packages/properties.py` | `pytest -q tests/test_z3_actual.py` | IMPLEMENTED BUT UNVERIFIED | 2 runtime tests skipped |
| PostgreSQL atomic claims and migrations | `packages/verification_jobs.py`, `alembic/versions/` | `pytest -q tests/test_postgres_integration.py tests/test_postgres_concurrency.py` | IMPLEMENTED BUT UNVERIFIED | 2 runtime tests skipped; SQLite migrations passed |
| React UI/API client runtime | `apps/web/src/` | Global TS syntax parse; `npm run typecheck` (failed missing deps) | IMPLEMENTED BUT UNVERIFIED | Cannot compile without real npm install |
| Genuine frontend lockfile and clean install | `apps/web/package.json` | `npm ci --offline`; npm registry attempt | NOT IMPLEMENTED | No `package-lock.json`; npm registry DNS unavailable |
| ESLint, Prettier, Vitest, Vite and Playwright | `apps/web/`, `apps/web/e2e/` | Corresponding `npm run ...` commands | IMPLEMENTED BUT UNVERIFIED | Tools unavailable; Playwright fixture now committed |
| CI correctness | `.github/workflows/test.yml` | PyYAML job parse | IMPLEMENTED BUT UNVERIFIED | Actual GitHub Actions executions not observed |
| Verification script data isolation | `scripts/verify.ps1`, `scripts/verify.sh` | Bash `-n`; `pytest -q tests/test_verify_script_safety.py` | VERIFIED PASS | Windows PowerShell script runtime not available here |
| Synthetic BM25 evaluation | `benchmarks/evaluate.py` | `python -m benchmarks.evaluate --output /mnt/data/pp_work/evidence/synthetic-benchmark` | VERIFIED PASS | Only six synthetic cases; not repair success |
| Real-world held-out repair trial | `benchmarks/repair_trials.py` | `pytest -q tests/test_repair_trials.py` | IMPLEMENTED BUT UNVERIFIED | No public defect archives / Docker / LLM model |
| Limited source secret-pattern scan | `scripts/security_scan.py` | `python -m scripts.security_scan` | VERIFIED PASS | Excludes Git history, generated assets and broader scanners |
| Ruff / mypy / dependency audit | CI workflow and `pyproject.toml` | `python -m ruff`, `python -m mypy`, `python -m pip_audit` | VERIFIED FAIL | Those dependencies unavailable in current environment |
| Clean Python 3.12 installation | `pyproject.toml` | Local Python version check | IMPLEMENTED BUT UNVERIFIED | Python 3.13.5 available, 3.12 not tested |
| Source handoff ZIP integrity | `PatchProof_Final_Local_Verification_Handoff.zip` | Zip CRC test and clean extraction after creation | VERIFIED PASS | Packaging is not production validation |
