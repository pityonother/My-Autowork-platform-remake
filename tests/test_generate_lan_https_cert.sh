#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "$0")" && pwd)}"
OPENSSL_BIN="${OPENSSL_BIN:-openssl}"
WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/my-autowork-ca-test.XXXXXX")"
trap 'rm -rf "$WORK_DIR"' EXIT

CA_KEY="$WORK_DIR/my-autowork-local-ca.key"
CA_CERT="$WORK_DIR/my-autowork-local-ca.crt"

# Reproduce the deployed legacy CA: it is a CA certificate but has no Key Usage.
"$OPENSSL_BIN" genrsa -out "$CA_KEY" 2048 >/dev/null 2>&1
"$OPENSSL_BIN" req -x509 -new -key "$CA_KEY" -sha256 -days 30 \
    -out "$CA_CERT" \
    -subj "/CN=My Autowork Local CA"

before_key_digest="$({
    "$OPENSSL_BIN" pkey -in "$CA_KEY" -pubout 2>/dev/null
} | "$OPENSSL_BIN" pkey -pubin -outform DER 2>/dev/null | "$OPENSSL_BIN" dgst -sha256)"

MY_AUTOWORK_SSL_DIR="$WORK_DIR" \
MY_AUTOWORK_LAN_IP="192.168.10.4" \
OPENSSL_BIN="$OPENSSL_BIN" \
    "$REPO_ROOT/generate_lan_https_cert.sh" >/dev/null

after_key_digest="$({
    "$OPENSSL_BIN" x509 -in "$CA_CERT" -pubkey -noout
} | "$OPENSSL_BIN" pkey -pubin -outform DER 2>/dev/null | "$OPENSSL_BIN" dgst -sha256)"

if [[ "$before_key_digest" != "$after_key_digest" ]]; then
    echo "CA repair unexpectedly replaced the existing private key." >&2
    exit 1
fi

certificate_text="$("$OPENSSL_BIN" x509 -in "$CA_CERT" -noout -text)"
basic_constraints="$(printf '%s\n' "$certificate_text" | awk '
    /X509v3 Basic Constraints: critical/ { getline; print; exit }
')"
key_usage="$(printf '%s\n' "$certificate_text" | awk '
    /X509v3 Key Usage: critical/ { getline; print; exit }
')"

[[ "$basic_constraints" == *"CA:TRUE"* ]] || {
    echo "CA certificate is missing critical CA:TRUE Basic Constraints." >&2
    exit 1
}
[[ "$key_usage" == *"Certificate Sign"* ]] || {
    echo "CA certificate is missing Certificate Sign Key Usage." >&2
    exit 1
}
[[ "$key_usage" == *"CRL Sign"* ]] || {
    echo "CA certificate is missing CRL Sign Key Usage." >&2
    exit 1
}

echo "CA extension regression test passed."
