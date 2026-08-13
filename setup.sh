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

# One rule for every Jaeger package: a sibling checkout WINS, the git
# URL is only the fallback. They are not on PyPI, so a requirements
# file can only name them by URL — and a URL requirement always forces
# a reinstall, which is how this used to clobber the editable installs
# made moments earlier and then fail on whatever @master happened to be.
#
# editable_mode=compat is NOT optional cosmetics. The default PEP 660
# editable install writes an import-HOOK (__editable___*_finder.py)
# that only runs at runtime; PyCharm and Pylance cannot follow it, so
# every `from jaeger_os...` import shows unresolved in the editor while
# working perfectly when you run it. compat writes a plain path
# instead, which static analysis reads.
install_jaeger() {          # $1 = sibling dir   $2 = repo name
  if [ -d "$1" ]; then
    echo "  $2  <- $1 (editable)"
    venv/bin/pip install --quiet -e "$1" \
      --config-settings editable_mode=compat
  else
    echo "  $2  <- github @master"
    venv/bin/pip install --quiet \
      "git+https://github.com/JenkinsRobotics/$2@master"
  fi
}

# Order matters: the framework first, because every module pins it.
#
# The framework plus the four imported providers Mochi currently composes:
# face, speech, hearing, and mind. JaegerAI is intentionally not part of this
# setup; it does not yet expose the same Mochi module contract as these
# providers.
install_jaeger ../JaegerOS         JaegerOS
install_jaeger ../JaegerAnimation  JaegerAnimation
install_jaeger ../JaegerKokoroTTS  JaegerKokoroTTS
install_jaeger ../JaegerWhisperSTT JaegerWhisperSTT
# The mind. Its repo and distribution are lower-case-hyphenated, unlike the
# four above — the directory name is the repo name, so the helper still works.
# llama-cpp-python rides along as a BASE dependency: the brain runs on this
# machine with no server and no API key.
install_jaeger ../jaeger-agent     jaeger-agent

# Dependencies only — the project itself is NOT installed. Mochi is a
# workspace you run from this directory, so core/ and interfaces/ are
# found on sys.path rather than in site-packages.
venv/bin/pip install --quiet -r requirements.txt
venv/bin/pip install --quiet pytest

echo
echo "ready:  source venv/bin/activate && python3 main.py"
venv/bin/python - <<'EOF'
import importlib, os
# Same switch main() sets: importing jaeger_agent registers ~96 tools,
# and a version check has no business paying for that.
os.environ.setdefault("JAEGER_AGENT_NO_TOOLS", "1")
for name in ("jaeger_os", "jaeger_animation", "jaeger_kokoro_tts",
             "jaeger_whisper_stt", "jaeger_agent"):
    try:
        print(f"  {name:20} {importlib.import_module(name).__version__}")
    except Exception as exc:
        print(f"  {name:20} NOT IMPORTABLE — {exc}")
EOF
