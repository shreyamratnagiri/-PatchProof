# Contributing

All contributions must treat uploaded source, issue text and model output as untrusted. Never add host execution of repository code or lower sandbox constraints to make a test pass. Add regression tests for security boundary changes, run `pytest`, `ruff`, `mypy`, frontend checks and benchmark scripts before proposing a release. Do not fabricate metrics or claim incomplete model/Docker paths are verified.

Prefer focused, typed changes with explicit failure states. Add new API operations with Pydantic schemas and UI endpoints; add migrations for persistent fields. Keep fixture datasets separate from measured outputs. Report missing dependencies as blockers rather than substituting mock production behavior.
