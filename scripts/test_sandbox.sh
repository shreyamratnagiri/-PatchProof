#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
command -v docker >/dev/null || { echo 'Docker CLI required' >&2; exit 2; }
docker info >/dev/null || { echo 'Start Docker daemon' >&2; exit 2; }
docker build -f docker/pytest-runner.Dockerfile -t patchproof-pytest:3.12-9.0.2 .
"${PATCHPROOF_PYTHON:-python3}" -m scripts.sandbox_smoke
"${PATCHPROOF_PYTHON:-python3}" -m pytest -q tests/test_docker_integration.py -rs
