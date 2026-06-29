#!/usr/bin/env bash
set -euo pipefail

OPENSSL_BIN="${OPENSSL_BIN:-openssl}"
SSL_DIR="${MY_AUTOWORK_SSL_DIR:-/Users/Shared/company_tools_data/my_autowork/ssl}"
HOSTNAME_VALUE="$(hostname -s 2>/dev/null || hostname 2>/dev/null || echo mac-mini)"

find_lan_ip() {
    local iface ip
    for iface in en0 en1 en2 en3 en4 en5 en6 en7 en8 en9; do
        ip="$(ipconfig getifaddr "$iface" 2>/dev/null || true)"
        case "$ip" in
            192.168.*|10.*|172.1[6-9].*|172.2[0-9].*|172.3[0-1].*)
                printf '%s\n' "$ip"
                return 0
                ;;
        esac
    done
}

LAN_IP="${MY_AUTOWORK_LAN_IP:-$(find_lan_ip)}"

if [ -z "$LAN_IP" ]; then
    echo "Could not detect LAN IP. Set MY_AUTOWORK_LAN_IP and retry." >&2
    exit 1
fi

mkdir -p "$SSL_DIR"
CA_KEY="$SSL_DIR/my-autowork-local-ca.key"
CA_CERT="$SSL_DIR/my-autowork-local-ca.crt"
SERVER_KEY="$SSL_DIR/my-autowork.key"
SERVER_CSR="$SSL_DIR/my-autowork.csr"
SERVER_CERT="$SSL_DIR/my-autowork.crt"
OPENSSL_CNF="$SSL_DIR/my-autowork-openssl.cnf"

if [ ! -f "$CA_KEY" ] || [ ! -f "$CA_CERT" ]; then
    "$OPENSSL_BIN" genrsa -out "$CA_KEY" 4096
    "$OPENSSL_BIN" req -x509 -new -nodes -key "$CA_KEY" -sha256 -days 3650 \
        -out "$CA_CERT" \
        -subj "/CN=My Autowork Local CA"
fi

cat > "$OPENSSL_CNF" <<EOF
[req]
default_bits = 2048
prompt = no
default_md = sha256
distinguished_name = dn
req_extensions = req_ext

[dn]
CN = My Autowork LAN

[req_ext]
subjectAltName = @alt_names

[alt_names]
DNS.1 = localhost
DNS.2 = $HOSTNAME_VALUE
IP.1 = 127.0.0.1
IP.2 = $LAN_IP
EOF

"$OPENSSL_BIN" genrsa -out "$SERVER_KEY" 2048
"$OPENSSL_BIN" req -new -key "$SERVER_KEY" -out "$SERVER_CSR" -config "$OPENSSL_CNF"
"$OPENSSL_BIN" x509 -req -in "$SERVER_CSR" -CA "$CA_CERT" -CAkey "$CA_KEY" -CAcreateserial \
    -out "$SERVER_CERT" -days 825 -sha256 -extensions req_ext -extfile "$OPENSSL_CNF"
rm -f "$SERVER_CSR"

echo "Generated LAN HTTPS certificate:"
echo "  CA certificate: $CA_CERT"
echo "  Server cert:    $SERVER_CERT"
echo "  Server key:     $SERVER_KEY"
echo "  LAN IP:         $LAN_IP"
