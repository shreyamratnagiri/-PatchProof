# Linux/macOS verification handoff

**Prerequisites:** Python 3.12, PostgreSQL 16, Node.js 22, Docker Engine/desktop, a supported Compose implementation, Git, and optionally Ollama with `nomic-embed-text` and `qwen2.5-coder:7b`. Linux containers are required for the Docker smoke cases. macOS also uses Docker Desktop.

```bash
cd patchproof
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
cp .env.example .env
```

Edit `.env` with a randomly generated, strong `PATCHPROOF_API_KEY` and distinct `PATCHPROOF_DB_PASSWORD`; never commit this file. Generate a key using `python -c 'import secrets; print(secrets.token_urlsafe(36))'`. Edit the database URL according to the environment. For a local database smoke test, start with SQLite; **PostgreSQL is a separate mandatory release check**.

Load **only named** config keys into your environment without running arbitrary shell directives from the file:

```bash
while IFS='=' read -r key value; do
  case "$key" in PATCHPROOF_API_KEY|PATCHPROOF_DB_PASSWORD|PATCHPROOF_DATABASE_URL|PATCHPROOF_DATA|PATCHPROOF_OLLAMA_URL|PATCHPROOF_PATCH_MODEL|PATCHPROOF_EMBED_MODEL) export "$key=$value";; esac
done < .env
alembic upgrade head
python -m pytest -q
```

**Full fail-closed verification:** `PATCHPROOF_PYTHON=.venv/bin/python scripts/verify.sh`. Logs land in `.verification-logs/` (gitignored). The script returns exit 1 if any required check fails, including missing Docker or Ollama. Do not mark the release complete with skipped gates.

For PostgreSQL on a trusted developer host:

```bash
docker compose up -d db
# Set PATCHPROOF_DATABASE_URL to postgresql+psycopg://patchproof:<URLENCODED_PASSWORD>@127.0.0.1:5432/patchproof
alembic upgrade head
```

Start the API without Docker control. A separate trusted worker must run on the host, sharing PostgreSQL and the repository artifact directory:

```bash
uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

In another terminal, run `cd apps/web && npm install && npm run build && npm test && npm run e2e && npm run dev`; open `http://127.0.0.1:5173`, enter the API key under System, and follow `docs/DEMO.md`. After a successful npm install, commit the generated `apps/web/package-lock.json`, then switch all CI and normal installation to `npm ci`.

Model checks require locally installed Ollama models:

```bash
ollama pull nomic-embed-text
ollama pull qwen2.5-coder:7b
python -m scripts.model_smoke
python -m scripts.sandbox_smoke
python -m scripts.repair_smoke
```

Any failed or unavailable gate must remain recorded in `FINAL_VALIDATION_REPORT.md`. The Docker runner does not provide hostile multi-tenant isolation. Never run imported tests directly on the host.

**Current verified topology:** `POST /api/repairs/{id}/verify` only enqueues a job; run `PATCHPROOF_DATA="$PWD/.runtime/data" .venv/bin/python -m packages.sandbox_worker --poll-seconds 1` separately. See `docs/TRUSTED_WORKER.md` for the exact security boundary. Run `scripts/test_sandbox.sh` and `scripts/run_repair_demo.sh` once Docker/Ollama have been installed.
