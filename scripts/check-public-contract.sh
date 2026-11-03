#!/usr/bin/env bash
set -euo pipefail

backend_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
frontend_root="${1:-"$backend_root/../UFES_Redes_Trab2_Frontend"}"

cmp "$backend_root/contracts/public/v1/events.json" \
  "$frontend_root/contracts/public/v1/events.json"
echo "Contrato público v1 sincronizado."
