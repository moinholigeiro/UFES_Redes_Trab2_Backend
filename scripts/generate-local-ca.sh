#!/usr/bin/env bash
set -euo pipefail
# No Git Bash (Windows), "/CN=..." do openssl viraria um caminho; em Linux a variável não tem efeito.
export MSYS_NO_PATHCONV=1

out_dir="${1:-artifacts/tls}"
extra_sans="${2:-}"
cert_days="${CERT_DAYS:-825}"
mkdir -p "$out_dir"
umask 077
lock_dir="$out_dir/.provision.lock"
if ! mkdir "$lock_dir" 2>/dev/null; then
  echo "provisionamento da CA já está em andamento ou lock existe: $lock_dir" >&2
  exit 2
fi
trap 'rmdir "$lock_dir" 2>/dev/null || true' EXIT

if [[ -e "$out_dir/ca.key" || -e "$out_dir/gateway.key" || -e "$out_dir/ca.crt" || -e "$out_dir/gateway.crt" || -e "$out_dir/ca.srl" ]]; then
  echo "Arquivos TLS já existem em $out_dir; nada foi sobrescrito. Rotacione manualmente." >&2
  exit 2
fi

tmp_dir="$(mktemp -d "$out_dir/.provision.XXXXXX")"
trap 'rm -f "$tmp_dir"/*; rmdir "$tmp_dir" 2>/dev/null || true; rmdir "$lock_dir" 2>/dev/null || true' EXIT

openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out "$tmp_dir/ca.key"
openssl req -x509 -new -sha256 -days 3650 \
  -key "$tmp_dir/ca.key" \
  -subj "/CN=UFES LLM Gateway Local CA" \
  -addext "basicConstraints=critical,CA:TRUE,pathlen:0" \
  -addext "keyUsage=critical,keyCertSign,cRLSign" \
  -out "$tmp_dir/ca.crt"

openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out "$tmp_dir/gateway.key"
openssl req -new -sha256 \
  -key "$tmp_dir/gateway.key" \
  -subj "/CN=localhost" \
  -out "$tmp_dir/gateway.csr"

ext_file="$tmp_dir/extensions"
sans="DNS:localhost,IP:127.0.0.1"
if [[ -n "$extra_sans" ]]; then
  if [[ ! "$extra_sans" =~ ^(DNS:[A-Za-z0-9._-]+|IP:[0-9A-Fa-f:.]+)(,(DNS:[A-Za-z0-9._-]+|IP:[0-9A-Fa-f:.]+))*$ ]]; then
    echo "SANs adicionais inválidos (use DNS:nome ou IP:endereço, separados por vírgula)" >&2
    exit 2
  fi
  sans="$sans,$extra_sans"
fi
if [[ ! "$cert_days" =~ ^[0-9]+$ ]] || (( cert_days < 1 || cert_days > 825 )); then
  echo "CERT_DAYS deve ser inteiro entre 1 e 825" >&2
  exit 2
fi
cat >"$ext_file" <<'EOF'
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
EOF
printf 'subjectAltName=%s\n' "$sans" >> "$ext_file"
  openssl x509 -req -sha256 -days "$cert_days" \
  -in "$tmp_dir/gateway.csr" \
  -CA "$tmp_dir/ca.crt" \
  -CAkey "$tmp_dir/ca.key" \
  -extfile "$ext_file" \
  -out "$tmp_dir/gateway.crt"

chmod 600 "$tmp_dir/ca.key" "$tmp_dir/gateway.key"
chmod 644 "$tmp_dir/ca.crt" "$tmp_dir/gateway.crt"
mv "$tmp_dir/ca.key" "$out_dir/ca.key"
mv "$tmp_dir/ca.crt" "$out_dir/ca.crt"
mv "$tmp_dir/gateway.key" "$out_dir/gateway.key"
mv "$tmp_dir/gateway.crt" "$out_dir/gateway.crt"
if [[ -e "$tmp_dir/ca.srl" ]]; then mv "$tmp_dir/ca.srl" "$out_dir/ca.srl"; fi
echo "CA e certificado local criados em $out_dir (SAN: $sans)."
