#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/home/bsnl/openloader}"
REPO_URL="${REPO_URL:-https://github.com/tanmodi/open_data_loader.git}"
BRANCH="${BRANCH:-main}"

if [[ "$(id -u)" -eq 0 ]]; then
  SUDO=""
else
  SUDO="sudo"
fi

install_packages() {
  $SUDO apt-get update
  $SUDO apt-get install -y ca-certificates curl git openssl

  if ! command -v docker >/dev/null 2>&1; then
    curl -fsSL https://get.docker.com | $SUDO sh
  fi

  $SUDO systemctl enable --now docker
}

sync_repo() {
  mkdir -p "$(dirname "$APP_DIR")"

  if [[ -d "$APP_DIR/.git" ]]; then
    git -C "$APP_DIR" fetch origin "$BRANCH"
    git -C "$APP_DIR" checkout "$BRANCH"
    git -C "$APP_DIR" pull --ff-only origin "$BRANCH"
  else
    rm -rf "$APP_DIR"
    git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
  fi
}

write_env() {
  if [[ ! -f "$APP_DIR/.env" ]]; then
    umask 077
    cat > "$APP_DIR/.env" <<EOF
DJANGO_SECRET_KEY=$(openssl rand -hex 32 2>/dev/null || date +%s%N)
EOF
  fi
}

start_app() {
  cd "$APP_DIR"
  $SUDO docker compose up -d --build
}

install_packages
sync_repo
write_env
start_app

echo "Open Data Loader is running on http://$(hostname -I | awk '{print $1}')/"
