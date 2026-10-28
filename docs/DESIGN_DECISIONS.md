# Design decisions

1. **Repository scope:** bounded ZIP and HTTPS GitHub imports only. GitHub blobs are accessed without checkout or executing hooks. Large repositories are rejected rather than silently indexed partially for safety.
2. **Language scope:** Python AST is the validated baseline. JavaScript/TypeScript uses tree-sitter if installed. Unsupported languages are skipped, and the scope limitation is disclosed.
3. **Semantic retrieval:** optional real local Ollama inference. An embedding-model outage is reported, not substituted with non-semantic token overlap.
4. **Ranking:** fixed, inspectable BM25 + cosine + one-hop dependency score to make ablation possible; no claim this necessarily improves ranking.
5. **Patch representation:** exact unique-string replacement allows a small auditable unified diff and reliable file scope validation. This deliberately excludes multi-file refactors and code transformations requiring arbitrary shell commands.
6. **Models:** explicit opt-in local provider, size-limited context, Pydantic schema, bounded retries and concurrency. No provider credentials are sent to an untrusted worker.
7. **Execution:** Docker-only. No host fallback, including on developer machines where Docker is missing. The trusted control plane must have access to a Docker daemon without passing socket into the untrusted container.
8. **Persistence:** SQLAlchemy schema, Alembic migrations, SQLite local mode, PostgreSQL deployment configuration. In-memory bounded generation queue is not reliable multi-node orchestration.
9. **Formal property proof:** Z3 can prove only implication between supplied quantifier-free integer constraints; it does not analyze or prove patched program semantics.
10. **Metrics:** per-case machine-readable results and explicit unavailability. Do not infer accuracy from passing unit tests or synthetic fixture retrieval alone.
