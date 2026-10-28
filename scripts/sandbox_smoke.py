"""Run trusted fixture scenarios exclusively in Docker; never execute a fixture on host."""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from packages.verification import verify

SCENARIOS = {
    'pass': ("import unittest\nclass TestOK(unittest.TestCase):\n    def test_ok(self): self.assertEqual(1+1,2)\n", 'passed', 15),
    'fail': ("import unittest\nclass TestFail(unittest.TestCase):\n    def test_fail(self): self.assertEqual(1+1,3)\n", 'failed', 15),
    'timeout': ("import unittest,time\nclass TestHang(unittest.TestCase):\n    def test_hang(self):\n        while True: time.sleep(0.1)\n", 'timeout', 2),
    'network': ("import unittest,socket\nclass TestNetwork(unittest.TestCase):\n    def test_denied(self):\n        with self.assertRaises(OSError):\n            socket.create_connection(('1.1.1.1',80),timeout=1)\n", 'passed', 15),
    'memory': ("import unittest\nclass TestMemory(unittest.TestCase):\n    def test_limit(self):\n        _ = bytearray(400 * 1024 * 1024)\n", 'failed', 15),
}


def main() -> int:
    if not shutil.which('docker'):
        print('BLOCKED: Docker CLI unavailable; no fixtures executed on host')
        return 2
    failures = []
    for name, (source, expected, timeout) in SCENARIOS.items():
        with tempfile.TemporaryDirectory(prefix='patchproof-smoke-') as tmp:
            root = Path(tmp)
            (root / 'tests').mkdir()
            (root / 'tests' / 'test_sandbox.py').write_text(source)
            result = verify(root, timeout=timeout)
        print(json.dumps({'scenario': name, 'expected': expected, 'observed': result['status'],
                          'duration_ms': result.get('duration_ms'), 'reason': result.get('reason')}, sort_keys=True))
        if result['status'] != expected:
            failures.append(name)
    check = subprocess.run(['docker', 'ps', '-a', '--filter', 'name=patchproof-', '--format', '{{.Names}}'],
                           capture_output=True, text=True, timeout=20, check=False)
    if check.returncode or check.stdout.strip():
        failures.append('cleanup')
    print('PASS' if not failures else 'FAIL: ' + ', '.join(failures))
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
