"""Best-effort defensive prompt redaction, not a substitute for secret scanning.

Do not send confidential repositories to an untrusted external model even when
these patterns are enabled. Unknown credential formats may not be detected.
"""
from __future__ import annotations

import re

_PEM = re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----.*?-----END (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----', re.S)
_ASSIGN = re.compile(
    r'''(?i)(?P<key>["']?(?:password|passwd|api[_-]?key|access[_-]?token|secret[_-]?key|auth[_-]?token|authorization)["']?\s*[:=]\s*["'])(?P<value>[^"'\r\n]{3,})(?P<close>["'])'''
)
_TOKENS = [
    re.compile(r'AKIA[0-9A-Z]{16}'),
    re.compile(r'gh[pousr]_[A-Za-z0-9_]{30,}'),
    re.compile(r'sk-[A-Za-z0-9_-]{20,}'),
    re.compile(r'(?i)Bearer\s+[A-Za-z0-9_.-]{20,}'),
]


def redact_sensitive(text: str) -> str:
    cleaned = _PEM.sub('[REDACTED_PRIVATE_KEY]', text)
    cleaned = _ASSIGN.sub(lambda found: found.group('key') + '[REDACTED]' + found.group('close'), cleaned)
    for token in _TOKENS:
        cleaned = token.sub('[REDACTED_CREDENTIAL]', cleaned)
    return cleaned
