# ATRIO Boardroom — Vultr deployment playbook

End-to-end deployment from a fresh Ubuntu 24.04 VM on Vultr to a public,
HTTPS-protected demo URL. Designed for the Milan AI Week 2026 submission.

## What you (the human) do first

### 1. Spin up the right VM

In Vultr → **Cloud Compute → Regular Performance** (NOT GPU; ATRIO is CPU-bound
because all inference is via Gemini/Featherless APIs).

| Field | Value |
|---|---|
| Plan | 4 vCPU / 8 GB RAM / 160 GB NVMe (~$48/mo, billed hourly) |
| Region | Frankfurt (FRA) or Amsterdam (AMS) — closest to Milan |
| OS | Ubuntu 24.04 LTS x64 |
| Hostname | `atrio-demo` |
| Label | `atrio-milan-aiweek-2026` |
| SSH key | Add via Account → SSH Keys before creating |

**Do NOT pick an NVIDIA instance.** A GPU costs ~10× more and we don't use it.

### 2. SSH key setup (from your laptop)

```powershell
ls $HOME\.ssh\id_ed25519.pub
# If not present:
ssh-keygen -t ed25519 -C "v_sen@verixa.dev" -f $HOME\.ssh\id_ed25519 -N '""'
Get-Content $HOME\.ssh\id_ed25519.pub | Set-Clipboard
```

Paste into Vultr → **Account → SSH Keys → Add SSH Key**. Select it when creating the VM.

### 3. After VM shows "Running"

Send Claude these three things:
1. **Public IPv4** (e.g. `45.32.x.y`)
2. Output of: `ssh root@<IP> "echo connected; uname -a"`
3. **A subdomain** like `atrio.verixa.dev` pointed at the IP (DNS A record).
   If no domain handy, we use bare IP + HTTP only; HTTPS via Let's Encrypt needs a domain.

## What Claude does next (after IP + DNS in hand)

### 4. Bootstrap (`deploy/01-bootstrap.sh`)

```bash
ssh root@<IP> bash -s < deploy/01-bootstrap.sh
```

Hardens SSH, installs Docker + Compose v2, configures `ufw` (22/80/443/8080 only),
installs fail2ban, sets timezone, prepares /srv/atrio.

### 5. Deploy (`deploy/02-deploy.sh`)

```bash
ssh root@<IP> bash -s < deploy/02-deploy.sh
```

Clones the repo into /srv/atrio, copies `deploy/prod.env.example` to `.env`,
brings up the stack via `docker compose --env-file .env up -d --build`,
waits for healthcheck, runs `alembic upgrade head`, calls the seed-demo endpoint.

### 6. Caddy + Let's Encrypt (`deploy/03-tls.sh`)

```bash
ssh root@<IP> DOMAIN=atrio.verixa.dev bash -s < deploy/03-tls.sh
```

Replaces the in-stack Caddyfile with a production version that serves on 443
with automatic Let's Encrypt for the provided domain. Falls back to bare IP if
DOMAIN is unset.

### 7. Verification

```bash
# Health
curl -s https://atrio.verixa.dev/api/v1/healthz | jq .
# Expected: { "status": "ok", "db": "ok", "inference_providers": { ... } }

# Run Playwright smoke against the public URL
WEB_BASE_URL=https://atrio.verixa.dev npm run test:e2e -w frontend -- smoke
```

## What gets deployed

| Service | Internal port | Public |
|---|---|---|
| Postgres 16 + pgvector | 5432 | none |
| MinIO | 9000 / 9001 | none |
| LiveKit | 7880 | proxied via Caddy /livekit |
| Mailhog | 8025 | none |
| API (FastAPI / uvicorn) | 8000 | proxied via Caddy /api/* |
| Frontend (Caddy SPA) | 8080 | **public URL (443 with TLS)** |

Single public entry: Caddy SPA container at 443.

## Cost

- VM: ~$48/mo billed hourly (= ~$0.07/hr)
- Demo window for judging (1 week up): ~$11
- Domain (if not owned): $12/yr at Cloudflare Registrar
- Outbound bandwidth: included (1 TB/mo)

Pause billing when not needed: `vultr-cli instance halt <id>`.

## Files in `deploy/`

| File | Purpose |
|---|---|
| `README.md` | this file |
| `01-bootstrap.sh` | One-shot OS hardening + Docker install |
| `02-deploy.sh` | Pull repo + start stack + run migrations + seed |
| `03-tls.sh` | Caddy + Let's Encrypt setup if DOMAIN provided |
| `prod.env.example` | Production env vars (keys, secrets, ports) |
| `Caddyfile.prod` | Production Caddy config with TLS |
