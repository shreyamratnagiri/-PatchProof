# Benchmarks

`benchmarks/fixtures/cases.json` contains six synthetic labeled cases. Run `python -m benchmarks.evaluate --output benchmarks/results` to reproduce and update machine-readable evidence.

**Authoring-environment measurement (Python 3.13, 2026-10-27):** BM25 Recall@1 = 5/6 (83.3%), Recall@5 = 6/6 (100%), MRR = 11/12 (0.9167). The measured median and p95 latency, peak Python allocation, and candidate order are in `benchmarks/results/aggregate.json` and `per_case.json`.

Semantic and graph-aware hybrid ranking are implemented but could not be benchmarked: no embedding-model service was available. **No claim of hybrid improvement** is warranted. These results should never be reported as real-world fault-localization or end-to-end bug-fixing accuracy.

## External real-repository snapshots (not run in authoring environment)

`benchmarks/public_defects.py` accepts JSONL with one held-out evaluation case per line, requiring `id`, `source_url` (upstream GitHub repository), full 40-character `revision`, `split: "test"`, `issue` (bug report), `archive` (locally supplied ZIP snapshot at that pinned revision), and `fault_files` (verified changed/defective file paths). It validates archive path safety and uses the exact same BM25/semantic/hybrid rankers. All source code is indexed as **data**; no repository tests run on the host.

Example schema (illustrative, **not** a measured real-world case):

```json
{"id":"example-123","source_url":"https://github.com/OWNER/REPOSITORY","revision":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","split":"test","issue":"Describe an independently confirmed bug with reproduction steps.","archive":"snapshot-example.zip","fault_files":["src/module.py"]}
```

Run: `python -m benchmarks.public_defects --manifest /path/to/cases.jsonl --output /path/to/real_results`. Independently verify issue provenance, commit IDs and gold file labels. Never put reference patches in the prompt. The evaluator measures **fault localization only**; it does not claim repair success, true SWE-bench accuracy or cross-project generalization. Without actual external cases and an embedding server those outcomes remain **unverified**.
