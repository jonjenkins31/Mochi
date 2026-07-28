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
# animation engine next door takes effect here without a reinstall.
#
# editable_mode=compat is NOT optional cosmetics. The default PEP 660
# editable install writes an import-HOOK (__editable___*_finder.py)
# that only runs at runtime; PyCharm and Pylance cannot follow it, so
# every `from jaeger_os...` import shows unresolved in the editor while
# working perfectly when you run it. compat writes a plain path
# instead, which static analysis reads.
for sib in ../JaegerOS ../JaegerAnimation; do
  [ -d "$sib" ] && venv/bin/pip install --quiet -e "$sib" \
      --config-settings editable_mode=compat 2>/dev/null || true
done
# Dependencies only — the project itself is NOT installed. Mochi is a
# workspace you run from this directory, so core/ and interfaces/ are
# found on sys.path rather than in site-packages.
venv/bin/pip install --quiet -r requirements.txt
venv/bin/pip install --quiet pytest

# The voice is opt-in: kokoro pulls torch, transformers and spacy —
# ~2 GB. A character player should not make everyone pay that to see a
# face. Sibling checkouts win when present, same as the framework.
if [ "${1:-}" = "--voice" ]; then
  echo "installing the voice (this pulls torch — a few minutes)..."
  for sib in ../JaegerKokoroTTS ../JaegerWhisperSTT; do
    [ -d "$sib" ] && venv/bin/pip install --quiet -e "$sib" \
        --config-settings editable_mode=compat && continue
    :
  done
  [ -d ../JaegerKokoroTTS ] || venv/bin/pip install --quiet -r requirements-voice.txt
fi

echo
echo "ready:  source venv/bin/activate && python3 main.py"
[ "${1:-}" = "--voice" ] || echo "        (voice not installed — ./setup.sh --voice)"
venv/bin/python -c "import jaeger_os, jaeger_animation; \
print(f'  jaeger-os {jaeger_os.__version__}  jaeger-animation {jaeger_animation.__version__}')"
