"""Evidence-based ordering, not a correctness probability or formal assurance score."""
from __future__ import annotations
from typing import Any


def candidate_priority(diff: str, result: dict[str, Any] | None) -> dict[str, Any]:
    """Explicit scoring: syntax +10; existing pass +50 / fail -40;
    regression fail-before-pass-after +30; up to -10 for edit size.

    Unavailable, timeout and unexecuted checks are never treated as passes.
    Never uses a model's unsupported confidence statement.
    """
    evidence = result or {}
    existing = evidence.get('existing_tests')
    regression = evidence.get('regression_tests')
    existing_status = existing.get('status', 'not_run') if isinstance(existing, dict) else 'not_run'
    regression_status = regression.get('status', 'not_run') if isinstance(regression, dict) else 'not_run'
    changes = sum(line.startswith('+') or line.startswith('-') for line in diff.splitlines() if not line.startswith(('+++', '---')))
    breakdown = {
        'syntax_valid': 10.0,
        'existing_tests': {'passed': 50.0, 'failed': -40.0}.get(existing_status, 0.0),
        'regression_tests': 30.0 if regression_status == 'passed' else 0.0,
        'edit_size': -round(min(10., changes * .2), 2),
    }
    return {'score': round(sum(breakdown.values()), 2), 'components': breakdown,
            'meaning': 'Relative evidence-based review priority, NOT patch correctness probability',
            'existing_tests': existing_status, 'regression_tests': regression_status}
