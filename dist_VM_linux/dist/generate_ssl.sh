#!/bin/bash
set -eu pipefail
#
# generate_ssl.sh
# ───────────────────────────────────────────────────────────────
# Create  "$CA_ROOT/$CERT_FILE"  and  "$CA_ROOT/$KEY_FILE"
# if they do not yet exist, honouring paths set in config.env.
#

# ── locate project root (identical to main_https.py) ───────────
if [[ -n "${_MEIPASS-}" ]]; then        # running from PyInstaller exe
    ROOT_DIR="$(dirname "$(dirname "$(readlink -f "$0")")")"
else                                     # dev / source checkout
    ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi

# ── load config.env (if present) ───────────────────────────────
OPENSSL=/usr/bin/openssl        # ← the CentOS-7 system binary
CONFIG_ENV="$ROOT_DIR/config.env"
if [[ -f "$CONFIG_ENV" ]]; then
    # shellcheck disable=SC1090
    source "$CONFIG_ENV"
fi

# ── configurable vars with sane defaults ───────────────────────
CA_ROOT="${CA_ROOT:-$ROOT_DIR/CA}"
CERT_FILE="${CERT_FILE:-server.crt}"
KEY_FILE="${KEY_FILE:-server.key}"

CRT="$CA_ROOT/$CERT_FILE"
KEY="$CA_ROOT/$KEY_FILE"

mkdir -p "$CA_ROOT"
# ── fallback to OpenSSL CLI (always exists on CentOS 7) ─────────
echo "[generate_ssl] (re)generating self-signed cert in $CA_ROOT …"
"$OPENSSL" req -x509 \
        -newkey rsa:2048 -nodes \
        -days 3650 \
        -subj "/CN=localhost" \
        -keyout "$KEY" \
        -out    "$CRT"

echo "[generate_ssl] ✔ created $CERT_FILE and $KEY_FILE"
