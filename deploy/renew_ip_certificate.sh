#!/usr/bin/env bash
# 由 systemd 定时续期 IP 证书，并让 Nginx 重新加载证书。
set -euo pipefail

public_ip="${1:?Usage: renew_ip_certificate.sh PUBLIC_IP}"
cd "$(dirname "$0")/.."

docker run --rm \
  -v /etc/letsencrypt:/etc/letsencrypt \
  -v /var/www/patent-check-certbot:/var/www/certbot \
  certbot/certbot:v5.4.0 renew --quiet --no-random-sleep-on-renew \
  --cert-name "$public_ip"

docker compose -f docker-compose.yml -f docker-compose.ip.yml exec -T nginx nginx -s reload
