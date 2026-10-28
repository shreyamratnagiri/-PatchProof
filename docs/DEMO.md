# End-to-end demo guide

Requirements: Python 3.12 with project dependencies, frontend npm dependencies, an application key, and Docker for actual test execution. Ollama is optional for generation, but required for model-backed patches and semantic/hybrid retrieval.

1. Start the API and frontend as described in `README.md`. Open the dashboard and set its API key in **System**.
2. Build a ZIP with a `calculator.py` containing `def add(a, b): return a - b` (valid Python with appropriate indentation) and a `tests/test_calculator.py` using Python unittest to assert `add(1,2)==3`.
3. Import the ZIP under **Repositories**. Select it to see the indexed Python file and graph. No source executes during this step.
4. Under **Investigate**, select the repository and report the incorrect arithmetic. Choose **BM25** so no model is required, and run fault localization.
5. Under **Patches**, choose the repair run. You may request a model proposal if Ollama is configured. Alternatively submit manual `old` = `return a - b`, `new` = `return a + b`, and a rationale. The candidate appears with a diff, and the imported file remains unchanged.
6. Click **Run Docker-isolated verification**. The API queues a durable job; start `python -m packages.sandbox_worker` in a separate trusted terminal. If Docker is unavailable the worker records an unverified result; otherwise it runs Python unittest inside a bounded disposable container. Generated regression tests, when provided, must fail on original source and pass on patched source to count as validated.
7. Export the report. It contains run provenance, candidate diffs, validation outcomes, and a warning that passing tests is not formal proof.

The model-backed fully autonomous path and Docker result are **not demonstrated** by the authoring-environment evidence. Never claim the sample is a fully autonomous solved bug without a configured model and recorded test outcomes.
