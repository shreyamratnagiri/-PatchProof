> **Historical audit:** This document describes the earlier 70-pass release candidate. The current candidate has 88 passing and 12 skipped tests. Refer to `../FINAL_VALIDATION_REPORT.md` and `RELEASE_REQUIREMENTS_MATRIX.md` for current evidence.

# Independent-style release gate matrix — source candidate (27 October 2026)

No automated rating is asserted; this is a source-level review. **VERIFIED PASS** applies only to observed commands and their narrow scope. See `FINAL_VALIDATION_REPORT.md` for exact logs and observations, and `REMAINING_LOCAL_VERIFICATION.md` for the local handoff.

| Requirement | Main implementation | Test or verification command | Status | Limitation |
| --- | --- | --- | --- | --- |
| Safe archive import, dedupe, ZIP resource controls | `packages/ingest.py`, `apps/api/main.py` | `pytest -q tests/test_core.py tests/test_release_features.py` | VERIFIED PASS | Public hostile operation out of scope |
| Public GitHub import / Git blob traversal | `packages/git_import.py` | `pytest -q tests/test_git_import.py` | VERIFIED PASS (pure logic) | Real GitHub fetch unverified |
| Bounded indexing and AST analysis | `packages/intelligence.py` | `pytest -q tests/test_analysis_new.py tests/test_index_budgets.py` | VERIFIED PASS | Accuracy and scale beyond fixtures not measured |
| JS/TS Tree-sitter parser | `packages/intelligence.py` | `python -c 'from packages.intelligence import _js_analysis; ...'` | IMPLEMENTED BUT UNVERIFIED | Native language pack absent here |
| BM25 retrieval | `packages/retrieval.py`, `benchmarks/evaluate.py` | `python -m benchmarks.evaluate` | VERIFIED PASS | Only six small synthetic cases |
| Embedding-based semantic retrieval | `packages/retrieval.py` | `python -m scripts.model_smoke` | IMPLEMENTED BUT UNVERIFIED | No Ollama inference executed |
| Hybrid graph-aware ranking | `packages/retrieval.py` | `benchmarks.evaluate`; deterministic vector tests | VERIFIED PASS for controlled vectors | Real-neural ablation unavailable |
| Real defect-snapshot adapter | `benchmarks/public_defects.py` | `pytest -q tests/test_public_benchmark.py` | VERIFIED PASS for simulated adapter tests | Genuine upstream corpus not obtained; repair rate unknown |
| Scoped structured patch proposals | `packages/repair.py` | `pytest -q tests/test_analysis_new.py tests/test_patch_scope.py` | VERIFIED PASS (schema/paths) | Real model-generated proposals unverified |
| Test source edit prevention | `packages/repair.py` | `pytest -q tests/test_patch_scope.py` | VERIFIED PASS | Other semantic attack patterns remain possible |
| Model generation and cancellation | `apps/api/main.py` | `pytest -q tests/test_release_features.py` | VERIFIED PASS for controlled model fixtures | In-memory single-process generation remains |
| Explicit candidate approval and export | `apps/api/main.py`, `alembic/versions/0003...` | `pytest -q tests/test_release_features.py` | VERIFIED PASS | Browser path unverified |
| Durable verification queue/claims | `packages/verification_jobs.py` | `pytest -q tests/test_worker_queue.py` | VERIFIED PASS for SQLite/controlled tests | PostgreSQL concurrency unverified |
| Dedicated PostgreSQL claims / rollback | `tests/test_postgres_concurrency.py` | `pytest -q tests/test_postgres_concurrency.py` with dedicated `_test` DB | IMPLEMENTED BUT UNVERIFIED | PostgreSQL service unavailable |
| Durable PostgreSQL schema and migrations | `alembic/versions/0001..0004`, `.github/workflows/test.yml` | `alembic upgrade head` | VERIFIED PASS on SQLite only | Actual PostgreSQL migrations unverified |
| API Docker socket separation | `docker-compose.yml`, `apps/api/main.py` | `pytest -q tests/test_compose_source.py` | VERIFIED PASS source contract | Docker Compose runtime unavailable |
| Trusted isolated execution | `packages/verification.py`, `packages/sandbox_worker.py` | `pytest -q tests/test_sandbox_options.py tests/test_node_sandbox_command.py` | VERIFIED PASS source contracts | Real Docker runs unverified |
| Container startup failure classification | `packages/verification.py` | `pytest -q tests/test_docker_error_classification.py` | VERIFIED PASS | No real Docker CLI here |
| Worker-owned orphan cleanup | `packages/sandbox_worker.py` | `pytest -q tests/test_orphan_cleanup.py` | VERIFIED PASS for controlled mock | Actual daemon restart test unverified |
| Node built-in JavaScript test runner | `packages/verification.py` | `pytest -q tests/test_node_sandbox_command.py` | VERIFIED PASS source command | Docker Node runtime unverified; TS/JSX execution unsupported |
| Z3 integer property checker | `packages/properties.py` | `pytest -q tests/test_z3_actual.py` | IMPLEMENTED BUT UNVERIFIED | Z3 package missing; cannot claim program proof |
| Non-root API volume ownership | `Dockerfile`, `docker-compose.yml` | Compose YAML parse and source test | IMPLEMENTED BUT UNVERIFIED | Runtime UID, host-worker file access not tested |
| React UI typed API integration | `apps/web/src` | Global TS `transpileModule` syntax parse | VERIFIED PASS only for syntax | Strict `tsc`, Vite, Vitest/Playwright unavailable |
| Committed genuine npm lockfile | `apps/web/package-lock.json` | `npm ci` | NOT IMPLEMENTED | Registry DNS `EAI_AGAIN`; CI correctly fails visibly |
| Python 3.12 / Ruff / mypy / audit | `pyproject.toml`, `.github/workflows/test.yml` | `pytest`, `ruff`, `mypy`, `pip-audit` in CI | IMPLEMENTED BUT UNVERIFIED | Python 3.12 and tools unavailable |
| Four explicit CI jobs | `.github/workflows/test.yml` | PyYAML parse | VERIFIED PASS for YAML syntax | GitHub Actions jobs not executed locally |
| Real model-driven repair success | `scripts/repair_smoke.py` | `python -m scripts.repair_smoke` | IMPLEMENTED BUT UNVERIFIED | Docker, Ollama, PostgreSQL required |
| Real-world end-to-end repair success rate | `benchmarks/public_defects.py` (localization only) | No observed full repair trials | NOT IMPLEMENTED | No real reference benchmark execution |
| Hostile multi-tenant isolation | `docs/SECURITY.md` | Out of scope for supported architecture | NOT APPLICABLE | Single-tenant trusted deployment only |

**Verdict:** Source release candidate for local integration and correction. The missing npm lockfile and unexecuted major runtime checks preclude a verified production release. Preserve failed/skipped statuses and seek real-world evidence before citing portfolio performance.

## 27 October 2026 — subsequent source review

| Requirement | Files | Evidence | Status | Remaining blocker |
| --- | --- | --- | --- | --- |
| Complete embedding batch validation | `packages/retrieval.py`; `tests/test_new_boundaries.py` | 6 new numerical/error cases in pytest | VERIFIED PASS (controlled provider contract) | Real Ollama embedding inference |
| Bounded directory walking | `packages/intelligence.py`; `tests/test_new_boundaries.py` | Empty-directory budget regression | VERIFIED PASS | Large-scale profiling |
| Portable default SQLite path | `packages/database.py`, `alembic/env.py`, `alembic.ini` | Successful SQLite migration from repository working directory | VERIFIED PASS on Linux | Actual Windows host confirmation |
| PostgreSQL queue budget coordination | `packages/verification_jobs.py` | Transaction advisory-lock path inspected; existing CAS tests pass | IMPLEMENTED BUT UNVERIFIED | Parallel PostgreSQL integration |
| Canonical file paths | `packages/ingest.py`; `tests/test_new_boundaries.py` | Malformed/control paths rejected | VERIFIED PASS | Broad hostile-input fuzzing |
| Genuine frontend `package-lock.json` | `apps/web/package.json`; `scripts/bootstrap_frontend.*` | npm registry DNS unavailable; offline npm ENOTCACHED | NOT IMPLEMENTED | Real npm registry |
| Frontend browser/production checks | `apps/web/src`; `apps/web/src/client.test.ts` | TS parser validates syntax only | IMPLEMENTED BUT UNVERIFIED | `npm ci`, strict tsc, ESLint, Prettier, Vitest, Vite, Playwright |
| Real held-out defect repair trials | `benchmarks/repair_trials.py`; `tests/test_repair_trials.py` | Runner fail-closed contract tests | IMPLEMENTED BUT UNVERIFIED | Provenance-reviewed corpus, Docker, Ollama |
| Complete Python test suite | `tests/` | `python -m pytest -q -rs`: **70 passed, 9 skipped** (Python 3.13.5) | VERIFIED PASS for 70 tests | Nine infrastructure skips + Python 3.12 |
| SQLite migrations | `alembic/` | `python -m alembic upgrade head`, versions 0001–0004 | VERIFIED PASS | PostgreSQL migrations unexecuted |
| Docker, Z3, PostgreSQL, Ollama live results | Existing modules and scripts | No supported services in this runtime | IMPLEMENTED BUT UNVERIFIED | Local/CI live runs |

The prior 58-test audit remains historical; **70 passed and 9 skipped** supersedes its local pytest count. A global `pip check` here fails due to the unrelated preinstalled MoviePy/Pillow mismatch, not an isolated PatchProof dependency solve. No unsupported score improvement is claimed.
