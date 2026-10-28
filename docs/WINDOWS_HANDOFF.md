# Windows verification and GitHub handoff

**This archive is a verification candidate, not the final production release.** It is intended to allow local testing of the previously blocked release gates. Do not describe incomplete or unavailable checks as passed.

## 0. Install prerequisites

Install Python **3.12**, Node.js **22**, Git, Docker Desktop (WSL 2 backend), and optionally Ollama. Start Docker Desktop and check that `docker version` prints both Client and Server. Windows PowerShell commands below assume you are in the extracted `patchproof` directory.

## 1. Configure Python and local data

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Edit `.env`: replace the example API key and database password with two distinct long, random secret strings. **Never push `.env`.** To generate a key on Windows, run:

```powershell
py -3.12 -c "import secrets; print(secrets.token_urlsafe(36))"
```

Load `.env` variables into your **current terminal** without evaluating shell commands:

```powershell
Get-Content .env | ForEach-Object {
  if ($_ -match '^([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
    [Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process')
  }
}
```

Use `PATCHPROOF_DATABASE_URL=sqlite:///./patchproof.db` initially. This local DB is easiest for an API smoke test, but does **not** replace the PostgreSQL release test. Run:

```powershell
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q apps/api packages benchmarks tests
.\.venv\Scripts\ruff.exe check packages apps/api benchmarks tests
.\.venv\Scripts\ruff.exe format --check packages apps/api benchmarks tests
.\.venv\Scripts\mypy.exe packages apps/api --ignore-missing-imports
.\.venv\Scripts\pip-audit.exe --progress-spinner off
.\.venv\Scripts\python.exe -m benchmarks.evaluate --output benchmarks/results
```

Record any failures rather than changing the reported results to green. The benchmark currently contains **synthetic fixtures**, not proof of real-world repair quality.

## 2. Verify PostgreSQL

```powershell
docker compose up -d db
docker compose ps
```

Before migration, in the **same** PowerShell window, set the database connection to use your configured password:

```powershell
$env:PATCHPROOF_DATABASE_URL = "postgresql+psycopg://patchproof:$($env:PATCHPROOF_DB_PASSWORD)@127.0.0.1:5432/patchproof"
.\.venv\Scripts\alembic.exe upgrade head
```

If your password includes reserved URL characters such as `@`, `:` or `/`, percent-encode it in the database URL. Re-run backend API/integration checks under PostgreSQL (note some test fixtures create their own SQLite engines).

## 3. Test the actual sandbox

```powershell
docker pull python:3.12-alpine
```

Run the API locally or in the Compose API container. **Neither is permitted to call Docker**. Start the dedicated host-side verification worker as described below. This is **not** authorization to execute uploaded source code directly on Windows. The application executes candidate tests only through restricted Docker containers.

**New trusted worker requirement:** Set `PATCHPROOF_DATA` to the absolute path of a directory shared by both the API and worker (use `Resolve-Path .runtime/data` after creating it). Configure `PATCHPROOF_DATABASE_URL` with the same PostgreSQL connection for both processes. Start the separate worker in **terminal B**:

```powershell
New-Item -ItemType Directory -Force .runtime/data | Out-Null
$env:PATCHPROOF_DATA = (Resolve-Path .runtime/data).Path
.\.venv\Scripts\python.exe -m packages.sandbox_worker --poll-seconds 1
```

Leave this terminal running for the demonstration. The API only queues jobs; no Docker socket is required or permitted in the API.

Start the API in terminal A (with `.env` loaded and database migrated):

```powershell
.\.venv\Scripts\uvicorn.exe apps.api.main:app --host 127.0.0.1 --port 8000
```

Visit `http://127.0.0.1:8000/health` and `http://127.0.0.1:8000/ready`. The ready response should report Docker availability; a healthy endpoint alone **does not** establish sandbox correctness.

## 4. Frontend build, tests, and browser test

Terminal B:

```powershell
cd apps/web
npm install
npm run typecheck
npm run build
npm test
npm run lint
npm run format:check
npx playwright install chromium
npm run e2e
npm run dev
```

Open `http://127.0.0.1:5173`. In **System**, enter your API key. Use the sample calculator defect described in `docs/DEMO.md` to test repository import, investigation, manual candidate creation, Docker verification and report export. Model-generated patches also require a running Ollama model.

**Important:** The frontend currently has no `package-lock.json` because registry access was unavailable during development. After `npm install`, retain and commit the generated lockfile once dependencies are verified.

## 5. Optional real model validation

Install Ollama, then (subject to available RAM and downloads):

```powershell
ollama pull nomic-embed-text
ollama pull qwen2.5-coder:7b
ollama list
```

Run semantic and hybrid investigation and model patch generation from the dashboard. Record the model version, input issue, observed results, and failures. Do **not** call passing existing tests formal proof. This path was not exercised in the authoring environment.

## 6. GitHub push

First inspect `.gitignore` and ensure no secrets or private repositories are in the tracked tree. A scan is not sufficient without a manual inspection. Once you've run the checks:

```powershell
git init
git branch -M main
git add .
git status --short
git commit -m "Build PatchProof verification candidate"
```

Create an **empty private** GitHub repository named `PatchProof` (do not prepopulate its README or license). Substitute your real GitHub username:

```powershell
git remote add origin https://github.com/YOUR_USERNAME/PatchProof.git
git push -u origin main
```

You **may push an unfinished repo privately to run GitHub Actions**; label it a development candidate, not a final production release. Fix CI failures, preserve logs, update `FINAL_VALIDATION_REPORT.md`, and only then tag a final release. `docs/DEMO.md` defines the manual test flow.

## 7. Required final-release evidence

Capture a check table with actual **command, exit code, environment and observed result** for Python, Ruff, mypy, migrations on PostgreSQL, frontend TypeScript/build/component/browser tests, Docker passing/failing/timeout fixtures and cleanup, Ollama embedding and generation, complete repair workflow, export, repeatable held-out metrics, and a secret/dependency audit. If any mandatory gate fails, label the repo **development** and do not claim 9.5/10 readiness.

**Security:** Do not load unknown public repositories while doing first-time deployment testing. Docker containers do not establish sufficient isolation for hostile multi-tenant code; keep the app bound to loopback.

## Updated automated checks and approval workflow

After installation, run `scripts\verify.ps1` from PowerShell. This script executes the available release checks, logs results to `.verification-logs` and exits nonzero if a mandatory gate fails or an external service is unavailable. It does not silently certify skipped checks.

The UI now has public GitHub import, local-model health probing, generation cancellation, optional targeted regression source, a scoped Z3 checker, and explicit **Approve candidate for export → Download .patch** actions. These do not alter the imported source tree.

The latest schema includes Alembic revisions `0003` and `0004`, which adds `candidates.approved_at`. Run `alembic upgrade head` after updating source. Since the authoring environment lacks npm registry access, generate a real `package-lock.json` using `npm install` **once on your laptop**, commit it, and use `npm ci` afterward. Do not synthesize lockfile integrity hashes.

## Local release candidate verification scripts

With environment variables loaded, run `./scripts/verify.ps1` for backend, frontend and integration checks. For isolated sandbox scenarios use `./scripts/test_sandbox.ps1`, and for a model-generated repair demonstration use `./scripts/run_repair_demo.ps1`. These must return nonzero on failure and depend on real Docker, Ollama, PostgreSQL, and npm availability. The repository currently has **no npm-generated lockfile** because package registry access failed in the build environment. On a connected machine run `cd apps/web; npm install --package-lock-only; npm ci` before the frontend checks; commit the generated lockfile. Do not invent integrity hashes.

Read `docs/TRUSTED_WORKER.md` before running any submitted repository tests.

## 8. Required updates for this candidate

`docker compose up -d api` now runs the trusted volume ownership bootstrap and Alembic migration service before the non-root API starts. Ensure that the host worker and API share the same `.runtime/data` directory, and on Linux set host UID/GID explicitly; never use world-writable permissions as a workaround.

Pull both sandbox images using `docker pull python:3.12-alpine` and `docker pull node:22-alpine`. The worker supports built-in Node.js `.js` test fixtures only; TypeScript/JSX execution is not verified. Read `REMAINING_LOCAL_VERIFICATION.md` for the **dedicated PostgreSQL `_test`** setup and exact commands. Do not expect `npm ci` to succeed until `apps/web/package-lock.json` has genuinely been generated with npm on a connected machine.

### Final local verification notes

The Playwright suite uses a committed, deterministic `apps/web/e2e/fixtures/calculator.zip` fixture. It starts a **disposable** local FastAPI/SQLite server; existing servers on the test ports are not reused. Stop any unrelated API/dev server before running `npm run e2e`. The verification script clears inherited PostgreSQL test URLs and uses a disposable SQLite database; use the dedicated PostgreSQL CI job to test a separate `_test` database.
