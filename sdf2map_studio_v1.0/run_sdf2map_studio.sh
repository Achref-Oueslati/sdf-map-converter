#!/usr/bin/env bash
set -euo pipefail
APP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if ! python3 -c 'import tkinter' >/dev/null 2>&1; then
  echo "Tkinter is missing. On Ubuntu, install it with: sudo apt install python3-tk" >&2
  exit 1
fi
exec python3 "$APP_DIR/sdf2map_studio.py"
