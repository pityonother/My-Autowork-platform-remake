#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
LABEL="com.local.my-autowork"
RUNTIME_DIR="${MY_AUTOWORK_RUNTIME_DIR:-$ROOT_DIR/shared_data/runtime}"
BACKUP_DIR="$ROOT_DIR/backups"
VENV_DIR="${MY_AUTOWORK_VENV:-$ROOT_DIR/.venv_macos}"
VENV_PY="$VENV_DIR/bin/python"

"$PYTHON_BIN" - <<'PY'
import sys

if sys.version_info < (3, 12):
    print(
        f"Python 3.12 or newer is required; current version is "
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}."
    )
    raise SystemExit(1)
PY

cd "$ROOT_DIR"

if [ ! -d ".git" ]; then
    echo "This folder is not a git repository."
    echo "First-time setup should use: git clone <repo-url> $ROOT_DIR"
    exit 1
fi

mkdir -p "$RUNTIME_DIR" "$BACKUP_DIR" "$ROOT_DIR/logs"

echo "Stopping service if it is installed..."
launchctl bootout "gui/$(id -u)" "$HOME/Library/LaunchAgents/$LABEL.plist" >/dev/null 2>&1 || true
pkill -f "uvicorn reconcile_web_app:app" >/dev/null 2>&1 || true

if [ -d "$RUNTIME_DIR" ]; then
    stamp="$(date +%Y%m%d_%H%M%S)"
    backup="$BACKUP_DIR/my_autowork_runtime_$stamp.tgz"
    echo "Backing up runtime data: $backup"
    tar -czf "$backup" -C "$RUNTIME_DIR" .
fi

echo "Pulling latest code..."
git fetch --all --prune
git pull --ff-only

echo "Refreshing Python environment..."
"$PYTHON_BIN" -m venv "$VENV_DIR"
"$VENV_PY" -m pip install -r "$ROOT_DIR/requirements.txt"

echo "Restarting service..."
if [ -f "$HOME/Library/LaunchAgents/$LABEL.plist" ]; then
    launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/$LABEL.plist"
    launchctl kickstart -k "gui/$(id -u)/$LABEL"
else
    nohup "$ROOT_DIR/run_mac_lan.sh" > "$ROOT_DIR/logs/my-autowork.out.log" 2> "$ROOT_DIR/logs/my-autowork.err.log" &
fi

echo "Update complete."
echo "Logs:"
echo "  $ROOT_DIR/logs/my-autowork.out.log"
echo "  $ROOT_DIR/logs/my-autowork.err.log"
