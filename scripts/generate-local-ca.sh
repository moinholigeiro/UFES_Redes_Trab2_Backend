#!/usr/bin/env bash
set -euo pipefail

out_dir="${1:-artifacts/tls}"
mkdir -p "$out_dir"
umask 077

if [[ -e "$out_dir/ca.key" || -e "$out_dir/gateway.key" ]]; then
  echo "Chaves já existem em $out_dir; remova-as manualmente apenas se deseja rotacionar a CA." >&2
  exit 2
fi

openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out "$out_dir/ca.key"
openssl req -x509 -new -sha256 -days 3650 \
  -key "$out_dir/ca.key" \
  -subj "/CN=UFES LLM Gateway Local CA" \
  -addext "basicConstraints=critical,CA:TRUE,pathlen:0" \
  -addext "keyUsage=critical,keyCertSign,cRLSign" \
  -out "$out_dir/ca.crt"

openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out "$out_dir/gateway.key"
openssl req -new -sha256 \
  -key "$out_dir/gateway.key" \
  -subj "/CN=localhost" \
  -out "$out_dir/gateway.csr"

ext_file="$(mktemp "$out_dir/extensions.XXXXXX")"
trap 'rm -f "$ext_file" "$out_dir/gateway.csr"' EXIT
cat >"$ext_file" <<'EOF'
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=DNS:localhost,IP:127.0.0.1
EOF
openssl x509 -req -sha256 -days 825 \
  -in "$out_dir/gateway.csr" \
  -CA "$out_dir/ca.crt" \
  -CAkey "$out_dir/ca.key" \
  -CAcreateserial \
  -extfile "$ext_file" \
  -out "$out_dir/gateway.crt"

chmod 600 "$out_dir/ca.key" "$out_dir/gateway.key"
chmod 644 "$out_dir/ca.crt" "$out_dir/gateway.crt"
echo "CA e certificado local criados em $out_dir (SAN: localhost, 127.0.0.1)."
