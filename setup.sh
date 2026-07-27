#!/usr/bin/env bash
# Mochi — one-command bootstrap.
#
# Python 3.11 is REQUIRED, not preferred: jaeger-os pins >=3.11,<3.13
# (the voice path's kokoro dependency is what caps it). A 3.13 venv
# installs nothing and fails at `import jaeger_os` with a message that
# does not mention the version — which is exactly how this bit once.
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3.11}"
command -v "$PY" >/dev/null || {
  echo "need python3.11 (jaeger-os pins >=3.11,<3.13); set PYTHON= to override" >&2
  exit 1
}

[ -d venv ] || "$PY" -m venv venv
venv/bin/pip install --quiet --upgrade pip

# Sibling checkouts win when present — editing the framework or the
# animation engine next door should take effect here without a
# reinstall. Falls back to the git pins in pyproject.toml otherwise.
for sib in ../JaegerOS ../JaegerAnimation; do
  [ -d "$sib" ] && venv/bin/pip install --quiet -e "$sib" 2>/dev/null || true
done
venv/bin/pip install --quiet -e ".[dev]" || venv/bin/pip install --quiet -e .

echo
echo "ready:  source venv/bin/activate && python3 main.py"
venv/bin/python -c "import jaeger_os, jaeger_animation; \
print(f'  jaeger-os {jaeger_os.__version__}  jaeger-animation {jaeger_animation.__version__}')"
