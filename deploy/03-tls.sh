#!/usr/bin/env bash
# ATRIO Boardroom · TLS via Caddy + Let's Encrypt (03-tls.sh)
#
#   DOMAIN=atrio.verixa.dev ssh root@<IP> bash -s < deploy/03-tls.sh
#
# Replaces the in-stack Caddyfile with a production version that serves on
# 443 with automatic Let's Encrypt for the provided DOMAIN. Falls back to a
# loud warning if DOMAIN is unset (keeps :8080 HTTP-only).

set -euo pipefail
exec > >(tee -a /var/log/atrio-tls.log) 2>&1

TARGET_DIR="/srv/atrio/atrio-boardroom"
cd "$TARGET_DIR"

if [ -z "${DOMAIN:-}" ]; then
    echo "[tls] DOMAIN not set; staying on http://<IP>:8080 (no TLS)" >&2
    echo "[tls] To enable TLS later, re-run with:  DOMAIN=atrio.verixa.dev bash -s < deploy/03-tls.sh"
    exit 0
fi

echo "[tls] domain: $DOMAIN"

# Sanity check: DNS A record must resolve to this host
PUBLIC_IP=$(curl -fsS https://api.ipify.org || echo unknown)
RESOLVED=$(getent hosts "$DOMAIN" | awk '{ print $1 }' | head -n1 || echo unknown)
if [ "$RESOLVED" != "$PUBLIC_IP" ]; then
    echo "[tls] WARNING: $DOMAIN resolves to $RESOLVED but VM public IP is $PUBLIC_IP" >&2
    echo "[tls]          Let's Encrypt will fail until DNS propagates. Continuing anyway..."
fi

# Production Caddyfile -- replaces the dev one used in compose
cat > docker/caddy/Caddyfile.prod <<EOF
{
    email v_sen@verixa.dev
    auto_https on
}

# Redirect HTTP -> HTTPS for the domain
http://$DOMAIN {
    redir https://$DOMAIN{uri} permanent
}

# HTTPS production listener
https://$DOMAIN {
    encode zstd gzip

    # API routes (preserve prefix)
    handle /api/* {
        reverse_proxy api:8000
    }

    # LiveKit (websocket)
    handle /livekit/* {
        reverse_proxy livekit:7880
    }

    # SPA fallback
    handle {
        root * /srv/app
        try_files {path} /index.html
        file_server
    }

    log {
        output stdout
        format json
    }
}
EOF

echo "[tls] wrote docker/caddy/Caddyfile.prod"

# Patch docker-compose to use the prod Caddyfile + open 443
COMPOSE_OVERRIDE=docker/docker-compose.prod.yml
cat > "$COMPOSE_OVERRIDE" <<EOF
# Production override: TLS via Caddy + Let's Encrypt
services:
  caddy:
    ports:
      - "80:80"
      - "443:443"
      - "8080:8080"
    volumes:
      - ./docker/caddy/Caddyfile.prod:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    environment:
      - DOMAIN=$DOMAIN

volumes:
  caddy_data:
  caddy_config:
EOF

echo "[tls] wrote $COMPOSE_OVERRIDE"

# Reload with the override
docker compose \
    -f docker/docker-compose.yml \
    -f "$COMPOSE_OVERRIDE" \
    --env-file .env \
    up -d caddy

echo
echo "[tls] waiting 30s for Let's Encrypt cert issuance..."
sleep 30

# Verify
echo
echo "[tls] verifying https://$DOMAIN/api/v1/healthz"
if curl -fsS "https://$DOMAIN/api/v1/healthz" | jq . ; then
    echo "[tls] ✅ TLS up at https://$DOMAIN"
else
    echo "[tls] ⚠️  HTTPS not yet responding; check 'docker logs atrio-caddy-1' and DNS propagation"
fi
