#!/usr/bin/env bash
# 这个文件用于初始化阿里云 ECS 上运行专利审查系统所需的基础依赖。

set -euo pipefail

USE_TSINGHUA_MIRROR=0

usage() {
  cat <<'USAGE'
Usage: deploy/bootstrap_ecs.sh [options]

Options:
  --use-tsinghua-mirror   Switch supported Linux package sources to Tsinghua mirror before installing.
  -h, --help              Show this help.

Run this script on the ECS server as root before deploy_asqmsl_cn.sh when Docker,
Docker Compose, Nginx, Certbot, or rsync is missing.
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --use-tsinghua-mirror)
      USE_TSINGHUA_MIRROR=1
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

if [ "$(id -u)" -ne 0 ]; then
  echo "Please run this script as root." >&2
  exit 1
fi

detect_os() {
  if [ -r /etc/os-release ]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    OS_ID="${ID:-unknown}"
    OS_VERSION_ID="${VERSION_ID:-unknown}"
    OS_VERSION_CODENAME="${VERSION_CODENAME:-}"
  else
    OS_ID="unknown"
    OS_VERSION_ID="unknown"
    OS_VERSION_CODENAME=""
  fi
}

backup_file() {
  local file="$1"
  if [ -f "${file}" ] && [ ! -f "${file}.patent-backup" ]; then
    cp -a "${file}" "${file}.patent-backup"
  fi
}

enable_tsinghua_for_apt() {
  echo "== Switching apt sources to Tsinghua mirror =="
  if [ -f /etc/apt/sources.list ]; then
    backup_file /etc/apt/sources.list
    sed -i.bak \
      -e 's#http://archive.ubuntu.com/ubuntu/#https://mirrors.tuna.tsinghua.edu.cn/ubuntu/#g' \
      -e 's#http://security.ubuntu.com/ubuntu/#https://mirrors.tuna.tsinghua.edu.cn/ubuntu/#g' \
      -e 's#https://archive.ubuntu.com/ubuntu/#https://mirrors.tuna.tsinghua.edu.cn/ubuntu/#g' \
      -e 's#https://security.ubuntu.com/ubuntu/#https://mirrors.tuna.tsinghua.edu.cn/ubuntu/#g' \
      -e 's#http://mirrors.aliyun.com/ubuntu/#https://mirrors.tuna.tsinghua.edu.cn/ubuntu/#g' \
      -e 's#https://mirrors.aliyun.com/ubuntu/#https://mirrors.tuna.tsinghua.edu.cn/ubuntu/#g' \
      /etc/apt/sources.list
  fi

  if [ -d /etc/apt/sources.list.d ]; then
    find /etc/apt/sources.list.d -type f \( -name '*.list' -o -name '*.sources' \) -print0 |
      while IFS= read -r -d '' file; do
        backup_file "${file}"
        sed -i.bak \
          -e 's#http://archive.ubuntu.com/ubuntu/#https://mirrors.tuna.tsinghua.edu.cn/ubuntu/#g' \
          -e 's#http://security.ubuntu.com/ubuntu/#https://mirrors.tuna.tsinghua.edu.cn/ubuntu/#g' \
          -e 's#https://archive.ubuntu.com/ubuntu/#https://mirrors.tuna.tsinghua.edu.cn/ubuntu/#g' \
          -e 's#https://security.ubuntu.com/ubuntu/#https://mirrors.tuna.tsinghua.edu.cn/ubuntu/#g' \
          -e 's#http://mirrors.aliyun.com/ubuntu/#https://mirrors.tuna.tsinghua.edu.cn/ubuntu/#g' \
          -e 's#https://mirrors.aliyun.com/ubuntu/#https://mirrors.tuna.tsinghua.edu.cn/ubuntu/#g' \
          "${file}"
      done
  fi
}

enable_tsinghua_for_yum() {
  echo "== Switching yum/dnf repo base URLs to Tsinghua mirror where possible =="
  if [ -d /etc/yum.repos.d ]; then
    find /etc/yum.repos.d -type f -name '*.repo' -print0 |
      while IFS= read -r -d '' file; do
        backup_file "${file}"
        sed -i.bak \
          -e 's#https\?://mirrors.aliyun.com/centos/#https://mirrors.tuna.tsinghua.edu.cn/centos/#g' \
          -e 's#https\?://mirror.centos.org/centos/#https://mirrors.tuna.tsinghua.edu.cn/centos/#g' \
          -e 's#https\?://download.docker.com/linux/centos/#https://mirrors.tuna.tsinghua.edu.cn/docker-ce/linux/centos/#g' \
          "${file}"
      done
  fi
}

install_with_apt() {
  export DEBIAN_FRONTEND=noninteractive
  if [ "${USE_TSINGHUA_MIRROR}" = "1" ]; then
    enable_tsinghua_for_apt
  fi

  apt-get update
  apt-get install -y ca-certificates curl git rsync openssl nginx certbot

  if ! command -v docker >/dev/null 2>&1; then
    apt-get install -y docker.io
  fi

  if ! docker compose version >/dev/null 2>&1; then
    if apt-cache show docker-compose-v2 >/dev/null 2>&1; then
      apt-get install -y docker-compose-v2
    elif apt-cache show docker-compose-plugin >/dev/null 2>&1; then
      apt-get install -y docker-compose-plugin
    else
      echo "Docker Compose plugin package is unavailable in current apt sources." >&2
      echo "Retry with --use-tsinghua-mirror or install Docker's compose plugin for this Ubuntu release." >&2
      exit 20
    fi
  fi
}

install_with_yum_like() {
  local pkg_manager="$1"
  if [ "${USE_TSINGHUA_MIRROR}" = "1" ]; then
    enable_tsinghua_for_yum
  fi

  "${pkg_manager}" makecache -y || true
  "${pkg_manager}" install -y ca-certificates curl git rsync openssl nginx certbot

  if ! command -v docker >/dev/null 2>&1; then
    if "${pkg_manager}" list docker >/dev/null 2>&1; then
      "${pkg_manager}" install -y docker
    elif "${pkg_manager}" list docker-ce >/dev/null 2>&1; then
      "${pkg_manager}" install -y docker-ce docker-ce-cli containerd.io
    else
      echo "Docker package is unavailable in current yum/dnf sources." >&2
      echo "Retry with --use-tsinghua-mirror or configure a Docker repository for this system." >&2
      exit 21
    fi
  fi

  if ! docker compose version >/dev/null 2>&1; then
    if "${pkg_manager}" list docker-compose-plugin >/dev/null 2>&1; then
      "${pkg_manager}" install -y docker-compose-plugin
    else
      echo "Docker Compose plugin package is unavailable in current yum/dnf sources." >&2
      echo "Retry with --use-tsinghua-mirror or configure a Docker Compose plugin repository." >&2
      exit 22
    fi
  fi
}

configure_services() {
  systemctl enable --now docker
  systemctl enable --now nginx
}

configure_docker_mirror() {
  mkdir -p /etc/docker
  if [ ! -f /etc/docker/daemon.json ]; then
    cat >/etc/docker/daemon.json <<'JSON'
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io"
  ]
}
JSON
    systemctl restart docker
  fi
}

detect_os
echo "== Detected OS: ${OS_ID} ${OS_VERSION_ID} ${OS_VERSION_CODENAME} =="

if command -v apt-get >/dev/null 2>&1; then
  install_with_apt
elif command -v dnf >/dev/null 2>&1; then
  install_with_yum_like dnf
elif command -v yum >/dev/null 2>&1; then
  install_with_yum_like yum
else
  echo "Unsupported Linux distribution: no apt-get, dnf, or yum found." >&2
  exit 3
fi

configure_services
configure_docker_mirror

echo
echo "== Installed versions =="
docker --version
docker compose version
nginx -v
certbot --version

echo
echo "ECS bootstrap finished."
