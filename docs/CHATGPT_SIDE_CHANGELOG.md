# Last ChatGPT-side pass — precise source change log

Continued **in place** from the existing release candidate. Changes were constrained to existing mandatory workflows.

| File | Reason and resulting behavior |
| --- | --- |
| `packages/verification.py` | Detect bare top-level pytest functions and async pytest functions without `import pytest`; attach missing-dependency/collection-error failure categories; bound empty directory traversal in sandbox staging. Never treat zero tests as success. |
| `packages/sandbox_worker.py` | Enforce copy budgets before trusted-worker staging, exclude local secret/tooling directories from disposable copies, renew long-running verification leases, classify unsupported/unavailable/timed-out/cancelled outcomes distinctly in candidate state. |
| `packages/verification_jobs.py` | Add ownership-checked lease renewal that cannot resurrect cancelled jobs; serialize created-at as UTC across SQLite/PostgreSQL. |
| `apps/api/main.py` | Return complete persisted repair-run shape on initial localization, matching `GET /api/repairs/{id}`; normalize SQLite-naive persisted UTC timestamps. |
| `benchmarks/repair_trials.py` | Enforce source-copy budgets and avoid untrusted symlink dereference/excess copied build artifacts in evaluation workspaces. |
| `apps/web/package.json` | Add pinned `@types/node` needed by Node/Vite/Playwright config typings. No fabricated lockfile. |
| `apps/web/playwright.config.ts` | Do not silently connect browser tests to an existing non-disposable API server or its database. |
| `apps/web/e2e/fixtures/calculator.zip` | Add the deterministic fixture previously referenced by the committed Playwright repair-flow test but missing from its archive. Fixture is intentionally defective and is *not* model evidence. |
| `.gitignore`, `.dockerignore` | Exclude TypeScript incremental metadata and host secrets/build caches; `.dockerignore` is newly added. |
| `scripts/verify.sh`, `scripts/verify.ps1` | Write synthetic benchmark output to the invocation's disposable workspace; drop inherited PostgreSQL integration URLs; Windows uses `npm.cmd` instead of a potentially execution-policy-blocked `npm.ps1`. |
| `scripts/bootstrap_frontend.ps1` | Use the official npm command shim without requiring PowerShell execution-policy changes. |
| `tests/test_pytest_sandbox_contract.py` | Regression tests for framework selection, missing imports, collection failures, and directory-budget rejection. |
| `tests/test_worker_queue.py` | Regression tests for owner-only lease renewal/cancellation and unsupported-target statuses. |
| `tests/test_browser_fixture.py` | Verify the browser fixture genuinely imports and browser runner never reuses a live server. |
| `tests/test_api_workflow.py` | Verify create-repair and retrieval return matching contracts, including timezone normalization. |
| `docs/WINDOWS_HANDOFF.md`, `REMAINING_LOCAL_VERIFICATION.md`, `docs/RELEASE_REQUIREMENTS_MATRIX.md`, `FINAL_VALIDATION_REPORT.md` | Record corrected Windows handoff, source/test matrix, actual checks, and unresolved gates. |

No model outcomes, Docker test results, browser screenshots, or npm integrity hashes have been invented.
