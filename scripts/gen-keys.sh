#!/usr/bin/env bash
# Generate the RSA keypair used by the API to sign access/refresh tokens.
#
# Usage:  ./scripts/gen-keys.sh
# Output: secrets/jwt_private.pem  +  secrets/jwt_public.pem
#
# These files are mounted into the API container at /run/secrets/* in
# docker-compose, and pointed at via JWT_PRIVATE_KEY_PATH / JWT_PUBLIC_KEY_PATH.
# Do NOT commit them — secrets/ is in .gitignore.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SECRETS_DIR="$REPO_ROOT/secrets"
PRIV="$SECRETS_DIR/jwt_private.pem"
PUB="$SECRETS_DIR/jwt_public.pem"

mkdir -p "$SECRETS_DIR"
chmod 700 "$SECRETS_DIR"

if [[ -f "$PRIV" && -f "$PUB" ]]; then
    echo "Keys already exist at $SECRETS_DIR — refusing to overwrite."
    echo "Delete them manually if you really want a fresh pair."
    exit 1
fi

echo "Generating RSA 4096-bit keypair…"
openssl genpkey -algorithm RSA -out "$PRIV" -pkeyopt rsa_keygen_bits:4096
openssl rsa -in "$PRIV" -pubout -out "$PUB"

chmod 600 "$PRIV"
chmod 644 "$PUB"

echo "✓ wrote $PRIV"
echo "✓ wrote $PUB"
echo
echo "Now set in .env:"
echo "  JWT_PRIVATE_KEY_PATH=$PRIV"
echo "  JWT_PUBLIC_KEY_PATH=$PUB"
