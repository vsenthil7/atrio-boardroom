#!/usr/bin/env bash
# ATRIO Boardroom · Vultr bootstrap (01-bootstrap.sh)
# Run on a fresh Ubuntu 24.04 LTS x64 VM via:
#   ssh root@<IP> bash -s < deploy/01-bootstrap.sh
#
# Idempotent: safe to re-run.

set -euo pipefail
exec > >(tee -a /var/log/atrio-bootstrap.log) 2>&1

echo "[bootstrap] start $(date -u +%FT%TZ)"

# ----- OS basics + security -----
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get upgrade -y
apt-get install -y --no-install-recommends \
    ca-certificates curl gnupg lsb-release ufw fail2ban \
    git make jq htop tmux unattended-upgrades \
    ufw apt-listchanges

# ----- Timezone -----
timedatectl set-timezone Europe/London || true

# ----- Unattended security updates -----
dpkg-reconfigure -plow unattended-upgrades || true

# ----- ufw firewall -----
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'ssh'
ufw allow 80/tcp comment 'http (caddy le-challenge + redirect)'
ufw allow 443/tcp comment 'https (caddy)'
ufw allow 8080/tcp comment 'http demo until tls is up'
ufw --force enable

# ----- SSH hardening -----
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^#\?ChallengeResponseAuthentication.*/ChallengeResponseAuthentication no/' /etc/ssh/sshd_config
systemctl reload ssh

# ----- fail2ban -----
systemctl enable --now fail2ban

# ----- Docker -----
if ! command -v docker >/dev/null 2>&1; then
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo \
        "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
        https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
        > /etc/apt/sources.list.d/docker.list
    apt-get update -y
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    systemctl enable --now docker
fi

# ----- Project dir -----
mkdir -p /srv/atrio
chown -R root:root /srv/atrio

# ----- Summary -----
echo "[bootstrap] docker: $(docker --version)"
echo "[bootstrap] compose: $(docker compose version)"
echo "[bootstrap] ufw status:"
ufw status verbose
echo "[bootstrap] done $(date -u +%FT%TZ)"
echo
echo "Next: ssh root@<IP> bash -s < deploy/02-deploy.sh"
