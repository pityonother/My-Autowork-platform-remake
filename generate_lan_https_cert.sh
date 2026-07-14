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
CA_OPENSSL_CNF="$SSL_DIR/my-autowork-ca-openssl.cnf"
SERVER_KEY="$SSL_DIR/my-autowork.key"
SERVER_CSR="$SSL_DIR/my-autowork.csr"
SERVER_CERT="$SSL_DIR/my-autowork.crt"
OPENSSL_CNF="$SSL_DIR/my-autowork-openssl.cnf"

cat > "$CA_OPENSSL_CNF" <<'EOF'
[req]
prompt = no
distinguished_name = dn
x509_extensions = v3_ca

[dn]
CN = My Autowork Local CA

[v3_ca]
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always
basicConstraints = critical, CA:TRUE
keyUsage = critical, keyCertSign, cRLSign
EOF

ca_key_matches_certificate() {
    local key_digest cert_digest
    key_digest="$(
        "$OPENSSL_BIN" pkey -in "$CA_KEY" -pubout 2>/dev/null \
            | "$OPENSSL_BIN" pkey -pubin -outform DER 2>/dev/null \
            | "$OPENSSL_BIN" dgst -sha256
    )" || return 1
    cert_digest="$(
        "$OPENSSL_BIN" x509 -in "$CA_CERT" -pubkey -noout 2>/dev/null \
            | "$OPENSSL_BIN" pkey -pubin -outform DER 2>/dev/null \
            | "$OPENSSL_BIN" dgst -sha256
    )" || return 1
    [ "$key_digest" = "$cert_digest" ]
}

ca_certificate_has_required_extensions() {
    local certificate_text basic_constraints key_usage
    certificate_text="$("$OPENSSL_BIN" x509 -in "$CA_CERT" -noout -text 2>/dev/null)" \
        || return 1
    basic_constraints="$(printf '%s\n' "$certificate_text" | awk '
        /X509v3 Basic Constraints: critical/ { getline; print; exit }
    ')"
    key_usage="$(printf '%s\n' "$certificate_text" | awk '
        /X509v3 Key Usage: critical/ { getline; print; exit }
    ')"
    case "$basic_constraints" in
        *CA:TRUE*) ;;
        *) return 1 ;;
    esac
    case "$key_usage" in
        *"Certificate Sign"*"CRL Sign"*) ;;
        *) return 1 ;;
    esac
}

if [ ! -f "$CA_KEY" ]; then
    "$OPENSSL_BIN" genrsa -out "$CA_KEY" 4096
    rm -f "$CA_CERT"
fi

if [ -f "$CA_CERT" ] && ! ca_key_matches_certificate; then
    echo "Existing CA certificate does not match the CA private key; refusing to replace it." >&2
    exit 1
fi

if [ ! -f "$CA_CERT" ] || ! ca_certificate_has_required_extensions; then
    "$OPENSSL_BIN" req -x509 -new -nodes -key "$CA_KEY" -sha256 -days 3650 \
        -out "$CA_CERT" \
        -config "$CA_OPENSSL_CNF" \
        -extensions v3_ca
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
