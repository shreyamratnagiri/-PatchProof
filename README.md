# PatchProof

**Development state: incomplete; NOT an approved production release.**

PatchProof is a repository investigation and experimental repair verification platform. It ingests a bounded repository ZIP or a public GitHub repository, indexes source files, ranks defect locations, accepts manual or opt-in model-generated replacement candidates, validates syntax, and provides evidence from optional Docker-isolated test runs. It never modifies the imported original during candidate creation or verification. It does **not** equate passing tests with formal correctness.

For Windows local testing, release-gate verification, and GitHub push, see **[docs/WINDOWS_HANDOFF.md](docs/WINDOWS_HANDOFF.md)**. See also **[docs/LINUX_HANDOFF.md](docs/LINUX_HANDOFF.md)** and **[docs/RELEASE_AUDIT.md](docs/RELEASE_AUDIT.md)** for cross-platform verification and the requirements matrix.

## Supported operations and limitations

| Capability | Current implementation |
| --- | --- |
| Authenticated ZIP import and duplicate detection | Implemented, exercised with API tests |
| Public GitHub HTTPS import | Implemented, offline external Git clone untested |
| Python AST extraction and static imports | Implemented, tested |
| JavaScript / TypeScript parser | Implemented via optional tree-sitter-language-pack, runtime not tested here |
| BM25 retrieval | Implemented, synthetic fixtures measured |
| Semantic embeddings | Real Ollama embedding endpoint; local model unavailable in authoring environment |
| Graph-aware hybrid ranking | Implemented; external embedding required, not benchmarked |
| Structured LLM patch proposals | Implemented via Ollama JSON output; no local model to test generation |
| Manual patch proposals | Implemented and API-tested, original repository preserved |
| Candidate regression test source | Implemented: targeted generated test must fail before patch and pass after patch, sandbox unverified |
| Docker isolated Python/Node test runner | Implemented and source-test-covered; Docker not available for real container execution; no host fallback |
| Supported Z3 linear implication | Implemented, z3-solver unavailable here; no source-code formal proof |
| PostgreSQL / Alembic | SQLAlchemy schema and migrations written; SQLite migration executed, PostgreSQL not run here |
| Authenticated web dashboard | React/TypeScript source included; Node registry unavailable, frontend build not verified |
| Bounded model jobs and cancellation | Implemented and unit-tested, single-process only |
| Explicit candidate approval and `.patch` export | Implemented and API-tested; never modifies imported originals |
| Candidate evidence priority | Deterministic source-based formula; not a correctness probability |
| Benchmark | Four strategy/ablation modes, six small synthetic cases, plus provenance-required external real-snapshot localization adapter; no genuine real-world repair measurement |

## Local development (requires Python 3.12)

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
# Edit .env and set a high entropy PATCHPROOF_API_KEY.
# Load only approved literal variables (never execute .env as a shell script):
while IFS='=' read -r key value; do
  case "$key" in
    PATCHPROOF_API_KEY|PATCHPROOF_DB_PASSWORD|PATCHPROOF_DATABASE_URL|PATCHPROOF_DATA|PATCHPROOF_OLLAMA_URL|PATCHPROOF_PATCH_MODEL|PATCHPROOF_EMBED_MODEL) export "$key=$value" ;;
  esac
done < .env
alembic upgrade head
uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

SQLite is the default local persistence path if the database environment variable is unset. For PostgreSQL, set `PATCHPROOF_DATABASE_URL` and run Alembic migrations first. The `docker-compose.yml` provides PostgreSQL, an automatic Alembic migration task, private directory ownership setup, and a non-root API. **The public API never has a Docker socket**. For Docker verification, run `python -m packages.sandbox_worker` as a separate operator-controlled host process, sharing the same PostgreSQL database and private artifact path. This is a security trade-off, not multi-tenant hardening.

From another terminal:

```bash
cd apps/web
npm install # npm registry needed; commit generated package-lock.json after successful install
npm run dev
```

Open `http://localhost:5173`. Navigate to **System** and enter the `PATCHPROOF_API_KEY`. The typed client calls the API through Vite proxy. No secret is stored in localStorage. See `docs/DEMO.md` for an end-to-end manual walkthrough.

### Optional local models

Install Ollama separately, obtain compatible models and configure `PATCHPROOF_OLLAMA_URL`, `PATCHPROOF_EMBED_MODEL`, and `PATCHPROOF_PATCH_MODEL`. Models are never downloaded or silently simulated by PatchProof. BM25 works without a model; semantic and hybrid ranking return an unavailable error if embedding inference cannot run.

### Tests and benchmarks

```bash
pytest -q
python -m compileall -q apps/api packages benchmarks
python -m benchmarks.evaluate --cases benchmarks/fixtures/cases.json --output benchmarks/results
# Requires installed optional tooling:
ruff check packages apps/api benchmarks scripts tests
ruff format --check packages apps/api benchmarks scripts tests
mypy packages apps/api --ignore-missing-imports
cd apps/web && npm run build && npm test && npm run e2e
```

For fail-closed test runners, use `scripts/verify.ps1` on Windows or `scripts/verify.sh` on Linux/macOS. These log and fail on missing dependencies. No uploaded code is tested on the host. Docker is mandatory for candidate execution. Dependencies and Docker availability are prerequisites, not permissions to execute unknown code outside isolation.

## Threat model

Assume repository contents and model responses are malicious. Archive extraction, path scope validation, bounded contexts, no LLM credentials in workers, localhost-bound services by default, and Docker sandbox constraints reduce risk. Container isolation is **not** a sufficient security boundary for arbitrary hostile public multi-tenant workloads. Do not expose this application publicly without additional isolation, authentication, rate limits, observability, and threat-model review.

## Repository layout

`apps/api` — authenticated FastAPI endpoints; `apps/web` — React/TypeScript dashboard; `packages` — persistence, ingestion, code analysis, retrieval, repair and verification; `alembic` — migrations; `benchmarks` — labeled synthetic fixtures plus external real-defect localization adapter; `tests` — API, algorithm, and security regression tests; `docs` — contracts, threat model, evaluation and demo; `.github/workflows` — CI commands.

## Engineering honesty

Read `FINAL_VALIDATION_REPORT.md` before describing PatchProof in a portfolio. This snapshot is **not** the final 9.5/10 release. A full real-model/real-Docker/frontend/PostgreSQL validation has not occurred, and no production safety or end-to-end autonomous repair reliability claim is made.

## Release candidate changes and status

This source includes a **durable database-backed verification queue**, a separate trusted host-side orchestrator (`python -m packages.sandbox_worker`), and migration `0004`. The API only queues Docker verification and provides job polling/cancellation; it cannot launch containers directly. See `docs/TRUSTED_WORKER.md` and `REMAINING_LOCAL_VERIFICATION.md`.

Source-level Python tests and SQLite migrations were run in the packaging environment. Docker, real Ollama inference, PostgreSQL runtime, full npm install/build, and Playwright were unavailable; do not assume they work until the target machine checks pass. React source-level syntax parsing is not equivalent to a Vite build.

## Updated source hardening in this release candidate

The candidate now enforces bounded indexing traversals, rejects candidates that edit test files, classifies Docker startup failures separately from test failures, and uses worker-job labels to request cleanup of abandoned sandbox containers. Simple JavaScript `node:test` cases can be executed inside a separate restricted Node container; JSX/TypeScript runtime verification remains **unsupported**. A real browser build, model-generated patch, PostgreSQL concurrency and container execution still require local evidence.

**GitHub Actions includes four independent gates:** backend, PostgreSQL `_test` integration, Docker sandbox, and React/Playwright. The frontend gate **intentionally fails until a genuine `apps/web/package-lock.json` is generated with npm and committed**. `npm ci` cannot be treated as reproducible without it.

For external historical defect **localization** evaluation, provide your own properly sourced held-out snapshot manifest to `python -m benchmarks.public_defects --manifest CASES.jsonl --output RESULTS`. Its values are not comparable to model repair success. Read `docs/BENCHMARKS.md` and `FINAL_VALIDATION_REPORT.md`.

## Latest source-level release-candidate audit (27 October 2026)

The updated archive includes the **existing** FastAPI application, React workspace,
trusted sandbox worker, and four database migrations. It additionally validates
neural embedding batch cardinality, limits empty-directory traversal, makes SQLite
paths portable, and uses a PostgreSQL transaction advisory lock for global queue
admission. The existing queue execution contract remains single-tenant.

Python unit/integration fixture run: **88 passed, 12 skipped** on Python 3.13.5.
This is *not* Python 3.12 acceptance, PostgreSQL runtime validation, or a clean
install. The twelve skipped tests require Docker (8), PostgreSQL (2), or Z3 (2).

A new `benchmarks/repair_trials.py` runner supports provenance-checked pinned
held-out snapshots: it requires a failing baseline Docker test, real model
candidates and passing post-patch Docker tests to report test-suite resolution.
It has **not** measured autonomous repair success on external defects yet.

**IMPORTANT: The npm lockfile is still missing**, because registry DNS queries
failed and the local npm cache does not contain all required packages. Run
`scripts/bootstrap_frontend.ps1` on Windows or `scripts/bootstrap_frontend.sh`
on Linux/macOS with working npm access to create the genuine lockfile, then
resolve any real TypeScript/ESLint/Prettier/Vitest/Vite failures. See
`REMAINING_LOCAL_VERIFICATION.md` for all other gates. Do not call the current
source release a production-verified repair platform.


### Pytest sandbox runner

To verify supported `tests/test_*.py` pytest repositories without network access
inside untrusted workloads, the trusted worker needs a locally built pytest
image. Build it on the **trusted host** before starting the worker:

```bash
docker build -f docker/pytest-runner.Dockerfile -t patchproof-pytest:3.12-9.0.2 .
```

The image includes only pinned pytest, not arbitrary project dependencies. A
missing dependency, collection failure, or zero collected tests remains
**unverified**, never a successful repair. See `docs/TRUSTED_WORKER.md`.


## Updated verification-candidate status

This source revision includes a trusted pytest container runner, strict zero-test
failure handling, a disposable database for both verification and model-repair
smoke scripts, non-root staging permission repair, and candidate deduplication.
See `FINAL_VALIDATION_REPORT.md` for commands actually executed and
`docs/RELEASE_REQUIREMENTS_MATRIX.md` for requirements and unverified checks.

**Important:** npm dependencies and `apps/web/package-lock.json` remain
unavailable in the authoring environment. The lockfile must be genuinely
generated with npm, committed and validated before the frontend CI gate can
pass. Real Docker, Ollama, PostgreSQL and Z3 integration are not yet verified.

## Last source-pass verification handoff

See [`docs/CHATGPT_SIDE_CHANGELOG.md`](docs/CHATGPT_SIDE_CHANGELOG.md), [`FINAL_VALIDATION_REPORT.md`](FINAL_VALIDATION_REPORT.md), and [`REMAINING_LOCAL_VERIFICATION.md`](REMAINING_LOCAL_VERIFICATION.md) for exact changes, attempted tests, failures, and the still-missing genuine frontend npm lockfile. This archive is a local-verification handoff, **not** a verified autonomous repair release.
