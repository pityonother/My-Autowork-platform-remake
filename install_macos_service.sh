#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
LABEL="com.local.my-autowork"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="$ROOT_DIR/logs"
COMPANY_TOOLS_DATA_ROOT="${COMPANY_TOOLS_DATA_ROOT:-/Users/Shared/company_tools_data}"
RUNTIME_DIR="${MY_AUTOWORK_RUNTIME_DIR:-$COMPANY_TOOLS_DATA_ROOT/my_autowork/runtime}"
PORT="${MY_AUTOWORK_PORT:-8010}"
SSL_DIR="${MY_AUTOWORK_SSL_DIR:-$COMPANY_TOOLS_DATA_ROOT/my_autowork/ssl}"
SSL_CERTFILE="${MY_AUTOWORK_SSL_CERTFILE:-$SSL_DIR/my-autowork.crt}"
SSL_KEYFILE="${MY_AUTOWORK_SSL_KEYFILE:-$SSL_DIR/my-autowork.key}"
SSL_CA_CERTFILE="${MY_AUTOWORK_SSL_CA_CERTFILE:-$SSL_DIR/my-autowork-local-ca.crt}"

"$PYTHON_BIN" - <<'PY'
import sys

if sys.version_info < (3, 12):
    print(
        f"Python 3.12 or newer is required; current version is "
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}."
    )
    raise SystemExit(1)
PY

mkdir -p "$HOME/Library/LaunchAgents" "$LOG_DIR" "$RUNTIME_DIR" "$SSL_DIR"
chmod +x "$ROOT_DIR/run_mac_lan.sh" "$ROOT_DIR/update_mac_mini.sh" "$ROOT_DIR/generate_lan_https_cert.sh"

if [ ! -f "$SSL_CERTFILE" ] || [ ! -f "$SSL_KEYFILE" ] || [ ! -f "$SSL_CA_CERTFILE" ]; then
    MY_AUTOWORK_SSL_DIR="$SSL_DIR" "$ROOT_DIR/generate_lan_https_cert.sh"
fi

cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$ROOT_DIR/run_mac_lan.sh</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$ROOT_DIR</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHON_BIN</key>
        <string>$PYTHON_BIN</string>
        <key>MY_AUTOWORK_OPEN_BROWSER</key>
        <string>0</string>
        <key>MY_AUTOWORK_HOST</key>
        <string>0.0.0.0</string>
        <key>MY_AUTOWORK_PORT</key>
        <string>$PORT</string>
        <key>MY_AUTOWORK_RUNTIME_DIR</key>
        <string>$RUNTIME_DIR</string>
        <key>MY_AUTOWORK_SSL_CERTFILE</key>
        <string>$SSL_CERTFILE</string>
        <key>MY_AUTOWORK_SSL_KEYFILE</key>
        <string>$SSL_KEYFILE</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$LOG_DIR/my-autowork.out.log</string>
    <key>StandardErrorPath</key>
    <string>$LOG_DIR/my-autowork.err.log</string>
</dict>
</plist>
PLIST

launchctl bootout "gui/$(id -u)" "$PLIST" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl enable "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
launchctl kickstart -k "gui/$(id -u)/$LABEL"

echo "Installed and started $LABEL"
echo "Logs:"
echo "  $LOG_DIR/my-autowork.out.log"
echo "  $LOG_DIR/my-autowork.err.log"
echo
echo "Check the LAN URL:"
echo "  tail -n 40 $LOG_DIR/my-autowork.out.log"
echo
echo "LAN HTTPS URL:"
echo "  https://$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo Mac-mini-IP):$PORT"
echo "Trust this CA certificate on coworker Windows PCs:"
echo "  $SSL_CA_CERTFILE"
