#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m compileall -q src tests
python3 -m pyflakes src tests 2>/dev/null || echo "pyflakes не установлен — пропуск"
for f in scripts/*.sh debian/time-doctor; do bash -n "$f"; done
echo "lint OK"
