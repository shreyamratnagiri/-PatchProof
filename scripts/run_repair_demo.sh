#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -f .env ]]; then
  while IFS='=' read -r key value; do
    case "$key" in
      PATCHPROOF_API_KEY|PATCHPROOF_DB_PASSWORD|PATCHPROOF_DATABASE_URL|PATCHPROOF_DATA|PATCHPROOF_OLLAMA_URL|PATCHPROOF_PATCH_MODEL|PATCHPROOF_EMBED_MODEL) export "$key=$value" ;;
    esac
  done <.env
fi
command -v docker >/dev/null || { echo 'Docker CLI required' >&2; exit 2; }
command -v ollama >/dev/null || { echo 'Ollama CLI required' >&2; exit 2; }
docker info >/dev/null || { echo 'Start Docker daemon' >&2; exit 2; }
# Real model/sandbox demo must not import fixtures into production storage.
demo_root="$(mktemp -d "${TMPDIR:-/tmp}/patchproof-repair-demo.XXXXXXXX")" || exit 1
chmod 700 "$demo_root"
trap 'rm -rf -- "$demo_root"' EXIT
mkdir -p "$demo_root/artifacts"
export PATCHPROOF_DATABASE_URL="sqlite:///$demo_root/demo.db"
export PATCHPROOF_DATA="$demo_root/artifacts"
"${PATCHPROOF_PYTHON:-python3}" -m scripts.repair_smoke
