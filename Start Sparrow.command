#!/bin/bash
# Double-click in Finder to run Sparrow locally (macOS). Close this window to stop it.
# First run: creates .venv and installs dependencies (about a minute). After that it just starts.
cd "$(dirname "$0")" || exit 1
URL="http://127.0.0.1:8000"

pause_exit() { echo; read -r -p "Press Return to close this window." _; exit 1; }

# Already running? Just open the browser.
if curl -sf "$URL/health" >/dev/null 2>&1; then
  echo "Sparrow is already running."
  open "$URL" 2>/dev/null || xdg-open "$URL" 2>/dev/null
  exit 0
fi

# Find Python 3.12 or newer (macOS's built-in python3 is usually 3.9, which is too old).
PY=""
for cand in python3.14 python3.13 python3.12 python3; do
  if command -v "$cand" >/dev/null 2>&1 &&
     "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
    PY="$cand"; break
  fi
done
if [ -z "$PY" ]; then
  echo "Sparrow needs Python 3.12 or newer, and none was found."
  echo "Install it from https://www.python.org/downloads/ (or: brew install python@3.12),"
  echo "then double-click this file again."
  open "https://www.python.org/downloads/" 2>/dev/null
  pause_exit
fi

# Create or refresh the virtualenv when it's missing, too old, or requirements changed.
REQ="backend/requirements-dev.txt"
STAMP=".venv/.sparrow-requirements"
WANT="$(cat backend/requirements.txt "$REQ" | shasum | cut -d' ' -f1)"
if ! .venv/bin/python -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
  echo "Setting up Python environment with $PY (first run only)..."
  rm -rf .venv
  "$PY" -m venv .venv || pause_exit
fi
if [ "$(cat "$STAMP" 2>/dev/null)" != "$WANT" ]; then
  echo "Installing dependencies..."
  .venv/bin/pip install -q --upgrade pip >/dev/null
  .venv/bin/pip install -q -r "$REQ" || pause_exit
  echo "$WANT" > "$STAMP"
fi

if [ -f config/commute.local.toml ]; then
  echo "Using your private stops (config/commute.local.toml)."
else
  echo "NOTE: config/commute.local.toml not found, so the public example stops are shown."
  echo "      See README.md > Configuration to add the real ones."
fi

# Open the browser once the server answers.
( for _ in $(seq 1 40); do
    if curl -sf "$URL/health" >/dev/null 2>&1; then open "$URL" 2>/dev/null || xdg-open "$URL" 2>/dev/null; break; fi
    sleep 0.5
  done ) &

echo
echo "Sparrow is running at $URL  (device preview: $URL/device)"
echo "Close this window (or press Ctrl+C) to stop it."
echo
cd backend && exec ../.venv/bin/uvicorn app.api.main:app --host 127.0.0.1 --port 8000
