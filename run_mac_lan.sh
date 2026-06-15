#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${MY_AUTOWORK_VENV:-$ROOT_DIR/.venv_macos}"
VENV_PY="$VENV_DIR/bin/python"
HOST="${MY_AUTOWORK_HOST:-0.0.0.0}"
PORT="${MY_AUTOWORK_PORT:-8010}"
COMPANY_TOOLS_DATA_ROOT="${COMPANY_TOOLS_DATA_ROOT:-/Users/Shared/company_tools_data}"
RUNTIME_DIR="${MY_AUTOWORK_RUNTIME_DIR:-$COMPANY_TOOLS_DATA_ROOT/my_autowork/runtime}"
OPEN_BROWSER="${MY_AUTOWORK_OPEN_BROWSER:-1}"

require_python312() {
    "$PYTHON_BIN" - <<'PY'
import sys

if sys.version_info < (3, 12):
    print(
        f"Python 3.12 or newer is required; current version is "
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}."
    )
    raise SystemExit(1)
PY
}

find_lan_ip() {
    local ip=""
    local iface=""

    for iface in en0 en1; do
        ip="$(ipconfig getifaddr "$iface" 2>/dev/null || true)"
        if [ -n "$ip" ]; then
            printf '%s\n' "$ip"
            return 0
        fi
    done

    iface="$(route get default 2>/dev/null | awk '/interface:/{print $2; exit}')"
    if [ -n "$iface" ]; then
        ip="$(ipconfig getifaddr "$iface" 2>/dev/null || true)"
        if [ -n "$ip" ]; then
            printf '%s\n' "$ip"
            return 0
        fi
    fi

    printf 'Mac-mini-IP\n'
}

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "python3 was not found. Install Python 3.12 on this Mac first."
    exit 1
fi
require_python312

if [ ! -x "$VENV_PY" ]; then
    echo "Creating Python virtual environment: $VENV_DIR"
    "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

echo "Installing dependencies..."
"$VENV_PY" -m pip install -r "$ROOT_DIR/requirements.txt"
if [ -f "$ROOT_DIR/requirements-yolo.txt" ]; then
    "$VENV_PY" -m pip install torch torchvision
    "$VENV_PY" -m pip install -r "$ROOT_DIR/requirements-yolo.txt"
fi

mkdir -p "$RUNTIME_DIR" "$ROOT_DIR/logs"
export BILL_TOOL_RUNTIME_DIR="$RUNTIME_DIR"

LAN_IP="$(find_lan_ip)"
LOCAL_URL="http://localhost:$PORT"
LAN_URL="http://$LAN_IP:$PORT"

echo
echo "My-Autowork LAN server"
echo "Project: $ROOT_DIR"
echo "Runtime: $RUNTIME_DIR"
echo "Local URL: $LOCAL_URL"
echo "LAN URL:   $LAN_URL"
echo
echo "Keep this terminal open while coworkers are using the app."
echo "Press Ctrl+C here to stop."
echo

if [ "$OPEN_BROWSER" = "1" ] && command -v open >/dev/null 2>&1; then
    open "$LOCAL_URL"
fi

exec "$VENV_PY" -m uvicorn reconcile_web_app:app \
    --host "$HOST" \
    --port "$PORT" \
    --log-level info
