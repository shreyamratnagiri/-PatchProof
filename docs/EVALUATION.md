# Evaluation protocol

The included benchmark corpus consists of six small, labeled, synthetic **held-out** local fixture programs; it is a smoke benchmark, not real-world performance evidence and not SWE-bench. The cases are fixed and not used for tuning within the harness, but this does not establish a rigorously held-out public benchmark. Each case has an issue description, candidate files, and one known faulty file. The benchmark imports no external datasets and executes none of the fixture code.

Four configurations are attempted: lexical BM25, embedding semantic, hybrid without graph, and hybrid with graph. If the real configured Ollama embedding endpoint is missing, semantic and hybrid results are reported as unavailable, never faked with token vectors. No hyperparameters are tuned on these six cases at evaluation time.

For each fully evaluated method: `Recall@k = cases with fault at rank <= k / evaluated cases`; `MRR = mean(1 / fault rank)`; median and empirical nearest-rank p95 retrieval latency are recorded. A summary for a method with missing cases is labeled incomplete and **does not** report aggregate scores.

Reproduction from repository root:

```bash
python -m benchmarks.evaluate --cases benchmarks/fixtures/cases.json --output benchmarks/results
pytest -q tests/test_benchmark.py
```

The benchmark saves `per_case.json` and `aggregate.json`. Python `tracemalloc` peak memory measures only traced Python allocations. The report does not measure model tokens or costs because model telemetry is not connected, patch resolution because no held-out autonomous repair evaluation has been run, or sandbox latency because Docker is unavailable here.

A credible follow-on study requires pinned public bug benchmark revisions, clean train/dev/test separation, a frozen ranking configuration, model and hardware provenance, real execution records, and confidence intervals across independent cases.
