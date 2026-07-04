#!/usr/bin/env bash
# 这个文件用于把专利审查系统同步并部署到 asqmsl.cn 的独立子域名或指定服务器。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

REMOTE="root@81.70.201.9"
REMOTE_DIR="/opt/patent_check_agent"
DOMAIN="check.asqmsl.cn"
WWW_DOMAIN=""
INSTALL_NGINX=1
DISABLE_CONFLICTING_NGINX=0
BOOTSTRAP_ECS=0
BOOTSTRAP_USE_TSINGHUA_MIRROR=0
ALLOW_ROOT_DOMAIN=0

usage() {
  cat <<USAGE
Usage: $0 [options]

Options:
  --remote USER@HOST              SSH target. Default: ${REMOTE}
  --remote-dir PATH               Remote app directory. Default: ${REMOTE_DIR}
  --domain DOMAIN                 Primary domain. Default: ${DOMAIN}
  --www-domain DOMAIN             WWW domain. Default: ${WWW_DOMAIN}
  --no-www                        Do not configure a www/secondary domain.
  --no-nginx                      Only sync and start Docker services.
  --disable-conflicting-nginx     Backup and remove existing Nginx configs that also match the domain.
  --bootstrap-ecs                 Install remote Docker, Compose, Nginx, Certbot, and rsync before deploy.
  --bootstrap-use-tsinghua-mirror Use Tsinghua Linux package mirrors during remote bootstrap.
  --allow-root-domain             Allow taking over asqmsl.cn. Use only after confirming the old site can be replaced.
  -h, --help                      Show this help.

Before running, make sure SSH login works and the remote .env has real production secrets.
To avoid overwriting the existing root site, prefer:
  $0 --domain check.asqmsl.cn --no-www
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --remote)
      REMOTE="${2:?Missing value for --remote}"
      shift 2
      ;;
    --remote-dir)
      REMOTE_DIR="${2:?Missing value for --remote-dir}"
      shift 2
      ;;
    --domain)
      DOMAIN="${2:?Missing value for --domain}"
      shift 2
      ;;
    --www-domain)
      WWW_DOMAIN="${2:?Missing value for --www-domain}"
      shift 2
      ;;
    --no-www)
      WWW_DOMAIN=""
      shift
      ;;
    --no-nginx)
      INSTALL_NGINX=0
      shift
      ;;
    --disable-conflicting-nginx)
      DISABLE_CONFLICTING_NGINX=1
      shift
      ;;
    --bootstrap-ecs)
      BOOTSTRAP_ECS=1
      shift
      ;;
    --bootstrap-use-tsinghua-mirror)
      BOOTSTRAP_USE_TSINGHUA_MIRROR=1
      shift
      ;;
    --allow-root-domain)
      ALLOW_ROOT_DOMAIN=1
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required local command: $1" >&2
    exit 1
  fi
}

shell_quote() {
  printf "%q" "$1"
}

require_command ssh
require_command rsync

cd "${REPO_ROOT}"

if [ "${DOMAIN}" = "asqmsl.cn" ] && [ "${ALLOW_ROOT_DOMAIN}" != "1" ]; then
  echo "Refusing to deploy to asqmsl.cn because that root domain already serves an existing site." >&2
  echo "Use a subdomain instead, for example:" >&2
  echo "  $0 --domain check.asqmsl.cn --no-www" >&2
  echo "If you are sure the old site can be replaced, rerun with --allow-root-domain." >&2
  exit 4
fi

if [ "${BOOTSTRAP_ECS}" = "1" ]; then
  echo "== Bootstrapping remote ECS dependencies =="
  bootstrap_args=""
  if [ "${BOOTSTRAP_USE_TSINGHUA_MIRROR}" = "1" ]; then
    bootstrap_args="--use-tsinghua-mirror"
  fi
  ssh "${REMOTE}" "cat >/tmp/patent_bootstrap_ecs.sh && chmod +x /tmp/patent_bootstrap_ecs.sh && /tmp/patent_bootstrap_ecs.sh ${bootstrap_args}" <"${REPO_ROOT}/deploy/bootstrap_ecs.sh"
fi

echo "== Preparing remote directory =="
ssh "${REMOTE}" "mkdir -p $(shell_quote "${REMOTE_DIR}")"

echo
echo "== Syncing project files =="
rsync -az --delete \
  --exclude ".git/" \
  --exclude ".env" \
  --exclude ".env.*" \
  --exclude "llm_api.md" \
  --exclude "node_modules/" \
  --exclude ".next/" \
  --exclude "out/" \
  --exclude "dist/" \
  --exclude "__pycache__/" \
  --exclude ".pytest_cache/" \
  --exclude ".mypy_cache/" \
  --exclude ".ruff_cache/" \
  --exclude ".venv/" \
  --exclude "venv/" \
  --exclude "uploads/" \
  --exclude "tmp/" \
  --exclude "logs/" \
  ./ "${REMOTE}:$(shell_quote "${REMOTE_DIR}")/"

echo
echo "== Running remote deployment =="
ssh "${REMOTE}" \
  "REMOTE_DIR=$(shell_quote "${REMOTE_DIR}") DOMAIN=$(shell_quote "${DOMAIN}") WWW_DOMAIN=$(shell_quote "${WWW_DOMAIN}") INSTALL_NGINX=$(shell_quote "${INSTALL_NGINX}") DISABLE_CONFLICTING_NGINX=$(shell_quote "${DISABLE_CONFLICTING_NGINX}") bash -s" <<'REMOTE_SCRIPT'
set -euo pipefail

cd "${REMOTE_DIR}"

set_env_value() {
  key="$1"
  value="$2"
  if grep -q "^${key}=" .env; then
    sed -i "s#^${key}=.*#${key}=${value}#" .env
  else
    printf '%s=%s\n' "${key}" "${value}" >>.env
  fi
}

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is not installed on the remote server. Install Docker first, then rerun this script." >&2
  exit 10
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose plugin is not available on the remote server. Install docker-compose-plugin first." >&2
  exit 11
fi

if ! docker info >/dev/null 2>&1; then
  echo "Current SSH user cannot access Docker. Fix Docker service or permissions first." >&2
  exit 12
fi

if [ ! -f .env ]; then
  cp deploy/asqmsl.cn.env.example .env
  chmod 600 .env
  echo "Created ${REMOTE_DIR}/.env from template."
  echo "Fill real production secrets in .env, then rerun this script." >&2
  exit 20
fi

set_env_value FRONTEND_URL "https://${DOMAIN}"
set_env_value NEXT_PUBLIC_API_BASE_URL "https://${DOMAIN}"

if grep -q "replace-with-" .env; then
  echo "Remote .env still contains placeholder values. Fill real production secrets, then rerun this script." >&2
  exit 21
fi

echo "== Starting Docker services =="
docker compose -f docker-compose.yml -f docker-compose.host-nginx.yml up -d --build postgres redis backend worker frontend
docker compose -f docker-compose.yml -f docker-compose.host-nginx.yml ps

echo
echo "== Checking local backend =="
curl -fsS "http://127.0.0.1:8000/api/health"
echo

if [ "${INSTALL_NGINX}" = "1" ]; then
  if [ "$(id -u)" -ne 0 ]; then
    echo "Nginx installation requires root SSH login. Rerun as root or use --no-nginx and configure Nginx manually." >&2
    exit 30
  fi

  backup_dir="/root/nginx-backup/asqmsl-cn-$(date +%Y%m%d%H%M%S)"
  mkdir -p "${backup_dir}"
  cp -a /etc/nginx/conf.d "${backup_dir}/conf.d" 2>/dev/null || true
  cp -a /etc/nginx/sites-enabled "${backup_dir}/sites-enabled" 2>/dev/null || true

  server_names="${DOMAIN}"
  if [ -n "${WWW_DOMAIN}" ]; then
    server_names="${server_names} ${WWW_DOMAIN}"
  fi
  conf_name="$(printf '%s' "${DOMAIN}" | tr -c 'A-Za-z0-9_.-' '_')"
  nginx_conf="/etc/nginx/conf.d/${conf_name}.conf"

  conflict_files=""
  search_files="$(grep -Rsl "server_name" /etc/nginx/conf.d /etc/nginx/sites-enabled 2>/dev/null || true)"
  while IFS= read -r file; do
    [ -n "${file}" ] || continue
    [ "${file}" = "${nginx_conf}" ] && continue
    if grep -q "server_name.*${DOMAIN}" "${file}"; then
      conflict_files="${conflict_files}${file}
"
      continue
    fi
    if [ -n "${WWW_DOMAIN}" ] && grep -q "server_name.*${WWW_DOMAIN}" "${file}"; then
      conflict_files="${conflict_files}${file}
"
    fi
  done <<EOF
${search_files}
EOF

  if [ -n "${conflict_files}" ]; then
    if [ "${DISABLE_CONFLICTING_NGINX}" != "1" ]; then
      echo "Found existing Nginx configs for ${DOMAIN}:" >&2
      echo "${conflict_files}" >&2
      echo "Review them first, then rerun with --disable-conflicting-nginx if this app should take over the domain." >&2
      exit 32
    fi

    echo "Backing up and disabling conflicting Nginx configs:"
    echo "${conflict_files}"
    while IFS= read -r file; do
      [ -n "${file}" ] || continue
      mkdir -p "${backup_dir}/disabled$(dirname "${file}")"
      cp -a "${file}" "${backup_dir}/disabled${file}"
      rm -f "${file}"
    done <<EOF
${conflict_files}
EOF
  fi

  if [ ! -f "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" ] || [ ! -f "/etc/letsencrypt/live/${DOMAIN}/privkey.pem" ]; then
    if ! command -v certbot >/dev/null 2>&1; then
      echo "Certbot is not installed. Rerun with --bootstrap-ecs or install certbot first." >&2
      exit 31
    fi

    echo "Issuing HTTPS certificate for ${server_names} without stopping the existing root site."
    mkdir -p /var/www/certbot
    sed \
      -e "s#__SERVER_NAMES__#${server_names}#g" \
      deploy/nginx/host-http-challenge.conf.template >"/tmp/${conf_name}.http.conf"
    install -m 0644 "/tmp/${conf_name}.http.conf" "${nginx_conf}"
    nginx -t
    systemctl reload nginx

    certbot_args="-d ${DOMAIN}"
    if [ -n "${WWW_DOMAIN}" ]; then
      certbot_args="${certbot_args} -d ${WWW_DOMAIN}"
    fi
    certbot certonly --webroot -w /var/www/certbot ${certbot_args} --agree-tos --no-eff-email --register-unsafely-without-email
  fi

  sed \
    -e "s#__SERVER_NAMES__#${server_names}#g" \
    -e "s#__CERT_DOMAIN__#${DOMAIN}#g" \
    deploy/nginx/host.conf.template >"/tmp/${conf_name}.conf"
  install -m 0644 "/tmp/${conf_name}.conf" "${nginx_conf}"
  nginx -t
  systemctl reload nginx
fi

echo
echo "== Public health checks =="
DOMAIN="${DOMAIN}" WWW_DOMAIN="${WWW_DOMAIN}" ./deploy/check_asqmsl_cn.sh
REMOTE_SCRIPT

echo
echo "Deployment finished for https://${DOMAIN}"
