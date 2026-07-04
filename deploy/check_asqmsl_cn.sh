#!/usr/bin/env sh
# 这个文件用于在服务器上检查专利审查系统部署后的域名和容器健康状态。

set -eu

DOMAIN="${DOMAIN:-check.asqmsl.cn}"
WWW_DOMAIN="${WWW_DOMAIN:-}"
COMPOSE_FILES="${COMPOSE_FILES:--f docker-compose.yml -f docker-compose.host-nginx.yml}"

echo "== Docker services =="
docker compose ${COMPOSE_FILES} ps

echo
echo "== Local backend health =="
curl -fsS "http://127.0.0.1:8000/api/health"
echo

echo
echo "== Codex CLI in worker =="
docker compose ${COMPOSE_FILES} exec -T worker codex --version

echo
echo "== Domain HTTPS health =="
curl -fsS "https://${DOMAIN}/api/health"
echo

if [ -n "${WWW_DOMAIN}" ]; then
  echo
  echo "== WWW HTTPS health =="
  curl -fsSI "https://${WWW_DOMAIN}" | sed -n '1,12p'
fi

echo
echo "== HTTP redirect =="
curl -fsSI "http://${DOMAIN}" | sed -n '1,8p'

echo
echo "== HTTPS headers =="
curl -fsSI "https://${DOMAIN}" | sed -n '1,12p'
