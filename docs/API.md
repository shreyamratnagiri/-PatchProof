# HTTP API v0.3

OpenAPI: `/docs` and `/openapi.json`. All `/api/*` endpoints require `X-PatchProof-Key: <value>`. `GET /health` and `/ready` are unauthenticated. Error responses use FastAPI `detail` messages and standard HTTP codes.

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/repositories/import` | multipart `file` ZIP; import, index, persist |
| POST | `/api/repositories/git` | JSON `{ "url": "https://github.com/owner/repo" }` |
| GET | `/api/repositories?limit=30&offset=0` | bounded listing |
| GET | `/api/repositories/{id}` | repository plus indexed entries |
| GET | `/api/repositories/{id}/graph` | nodes and import edges |
| GET | `/api/repositories/{id}/file?path=...` | bounded source reader |
| POST | `/api/issues` | `{repository_id,description,expected?,observed?}` |
| GET | `/api/issues?repository_id=...` | issue listing |
| POST | `/api/repairs` | `{issue_id,method:"lexical"|"semantic"|"hybrid",generate:false}` |
| GET | `/api/repairs` | repair run listing |
| GET | `/api/repairs/{id}` | run state and ranked locations |
| POST | `/api/repairs/{id}/generate` | schedules bounded model generation; returns job id |
| POST | `/api/repairs/{id}/candidates` | manual `{path,old,new,rationale,regression_test?}` |
| GET | `/api/repairs/{id}/candidates` | priority-ordered diffs and evidence |
| POST | `/api/repairs/{id}/candidates/{candidate_id}/approve` | Explicitly approve export; no mutation of imported source |
| GET | `/api/repairs/{id}/candidates/{candidate_id}/patch` | Approved unified `.patch` download; before approval returns 409 |
| POST | `/api/repairs/{id}/verify?candidate_id=...` | HTTP 202 queues persistent verification; returns `job_id`; worker performs isolated tests and regression checking |
| POST | `/api/repairs/{id}/properties` | bounded QF-LIA property proof for supplied constraints |
| GET | `/api/jobs/{id}` | Poll generation run or verification job; evidence included for verification jobs |
| POST | `/api/jobs/{id}/cancel` | Cancel pending/running model generation or sandbox verification |
| GET | `/api/repairs/{id}/report` | JSON report with download header |
| GET | `/api/jobs/{id}` | job status and explanation |
| POST | `/api/jobs/{id}/cancel` | request bounded generation cancellation |
| GET | `/api/status` | capability and limitation report |
| GET | `/api/model/health` | Real Ollama `/api/tags` health probe; listing is not inference |

Example localized workflow:

```bash
curl -H 'X-PatchProof-Key: YOUR_KEY' -F 'file=@sample.zip' http://127.0.0.1:8000/api/repositories/import
curl -H 'X-PatchProof-Key: YOUR_KEY' -H 'Content-Type: application/json' -d '{"repository_id":"UUID","description":"Function returns subtraction rather than addition"}' http://127.0.0.1:8000/api/issues
curl -H 'X-PatchProof-Key: YOUR_KEY' -H 'Content-Type: application/json' -d '{"issue_id":"UUID","method":"lexical","generate":false}' http://127.0.0.1:8000/api/repairs
```

See `docs/SECURITY.md` for suitability limits. There is no claim that a test exit code proves program correctness.
