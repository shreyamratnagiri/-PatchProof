# PatchProof — ChatGPT-side final source pass: factual validation report

**Release classification:** Local-verification handoff, **not** a verified production release or a demonstrated 9.5/10 implementation. Based on `PatchProof_Final_Release_Candidate.zip` (107 archived files; 88 Python tests passing at baseline); no architecture replacement.

## Environment

- Python **3.13.5**, not the requested clean Python 3.12 environment.
- Node **22.16.0**, npm **10.9.2**, global TypeScript compiler available for syntax parsing only.
- No Docker CLI/daemon, PostgreSQL test server, Ollama runtime, Z3 package, installed project-local npm dependencies, Ruff, mypy, or pip-audit.
- Real npm registry requests failed with DNS `EAI_AGAIN` to `registry.npmmirror.com`; the default registry lockfile-generation attempt timed out. No genuine `package-lock.json` could be generated; **none is included**. Never generate one by hand.
- The preinstalled Python environment is not a clean project-specific Python 3.12 environment.

## Actual commands and observations

| Status | Command executed (from repository root unless specified) | Observed result | Scope |
| --- | --- | --- | --- |
| VERIFIED PASS | `python -m pytest -q -rs` | **97 passed, 12 skipped** | Unit/API/database fixture/security regression tests; 12 missing-runtime tests not passed |
| VERIFIED PASS | `python -m compileall -q apps/api packages benchmarks tests scripts` | Exit 0 | Python syntax/bytecode compilation only |
| VERIFIED PASS | `PATCHPROOF_DATABASE_URL=sqlite:////mnt/data/pp_work/evidence/migrations_validation.db python -m alembic upgrade head` | Exit 0; revisions 0001–0004 applied | Disposable SQLite database |
| VERIFIED PASS | `python -c '... TestClient(app) ...'` (see `evidence/commands.json` audit record outside ZIP) | `/health=200`, `/ready=200`, protected no key `401`, authenticated `200` | Real local in-process FastAPI requests with disposable SQLite |
| VERIFIED PASS | `python -m benchmarks.evaluate --output /mnt/data/pp_work/evidence/synthetic-benchmark` | Exit 0 | Six synthetic cases; no measured model repair performance |
| VERIFIED PASS | `python -m scripts.security_scan` | No matching high-risk token patterns | Limited source pattern scan, not repository-history audit |
| VERIFIED PASS | `bash -n scripts/verify.sh scripts/run_repair_demo.sh scripts/test_sandbox.sh scripts/bootstrap_frontend.sh` | Exit 0 | Bash syntax only |
| VERIFIED PASS | `python -c 'import yaml; ... yaml.safe_load(.github/workflows/test.yml)'` | Four jobs parsed: backend, postgres, sandbox, frontend | YAML parsing, **not CI execution** |
| VERIFIED PASS | Global TypeScript `createSourceFile(...).parseDiagnostics` on seven TS/TSX sources | Seven files parsed without syntax errors | **Not** strict TypeScript or a frontend build |
| VERIFIED FAIL | `npm ci --ignore-scripts --offline` in `apps/web` | Nonzero, genuine lockfile missing | Frontend dependency reproducibility; not fixed |
| VERIFIED FAIL | `npm run typecheck`, `npm run build` in `apps/web` | TS2688: missing `vite/client` type definitions | Cannot complete frontend checks without npm install |
| VERIFIED FAIL | `npm run lint`, `npm run format:check`, `npm run test` | eslint/prettier/vitest not installed | No complete frontend validation |
| VERIFIED FAIL | `npm run e2e` | Playwright Node CLI unavailable | Browser tests **not** executed |
| VERIFIED FAIL | `python -m ruff check ...`, `python -m ruff format --check ...` | No module named ruff | Source formatting/lint not verified |
| VERIFIED FAIL | `python -m mypy packages apps/api --ignore-missing-imports` | No module named mypy | Strict Python typing not verified |
| VERIFIED FAIL | `python -m pip_audit --progress-spinner off` | No module named pip_audit | Third-party dependency vulnerabilities not audited |
| IMPLEMENTED BUT UNVERIFIED | `python -m pytest -q tests/test_docker_integration.py` | Eight Docker cases skipped | Docker sandbox isolation/runtime behavior |
| IMPLEMENTED BUT UNVERIFIED | `python -m pytest -q tests/test_postgres_integration.py tests/test_postgres_concurrency.py` | Two PostgreSQL cases skipped | Dedicated `_test` PostgreSQL integration |
| IMPLEMENTED BUT UNVERIFIED | `python -m pytest -q tests/test_z3_actual.py` | Two Z3 cases skipped | Scoped integer-property solver runtime |
| IMPLEMENTED BUT UNVERIFIED | `python -m scripts.model_smoke`, `python -m scripts.repair_smoke` | Not executed; Ollama/Docker unavailable | Genuine autonomous model repair |
| IMPLEMENTED BUT UNVERIFIED | `.github/workflows/test.yml` on GitHub-hosted runners | Not executed here | CI runs and clean-clone install |

**Evidence limits:** Failure due to missing tools is not the same as a reproducible code defect. No Docker, Ollama, PostgreSQL, Z3, live embedding, Vite build, or Playwright success is claimed. No real-repository resolution rate or 9.5/10 rating is claimed. The originally reported 88 Python tests remain passing; the expanded suite passes 97.

## Source changes and regressions

See `docs/CHATGPT_SIDE_CHANGELOG.md` for exact paths and rationale. Tests added for plain pytest discovery, collection/missing-dependency failures, directory budgeting, lease renewal ownership/cancellation, unsupported-target evidence, browser fixture presence, and consistent API run JSON/UTC timestamps.

## Remaining release blockers

1. **Frontend lockfile:** Run `scripts/bootstrap_frontend.ps1` on Windows with a working npm registry. It uses npm itself and does not fabricate hashes. Commit the generated `apps/web/package-lock.json` only after `npm ci`, TypeScript, ESLint, Prettier, Vitest and Vite pass. Run Playwright separately.
2. **Live infrastructure:** Build and execute Docker sandbox tests, run trusted worker with disposable fixture, start a dedicated PostgreSQL `_test` DB, execute actual Z3 package checks and real Ollama model tests.
3. **Quality gates:** Clean Python 3.12 install, Ruff/mypy checks, dependency scanning, and CI validation. Fix any genuine source defects discovered by those tests before calling the system production-ready.
4. **Real evaluation:** Held-out defect snapshots and model inference were not available. Synthetic BM25 figures must never be described as autonomous repair success.

For exact local commands and non-destructive setup use `REMAINING_LOCAL_VERIFICATION.md` and `docs/WINDOWS_HANDOFF.md`.
