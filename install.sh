#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/home/bsnl/openloader}"
REPO_URL="${REPO_URL:-https://github.com/tanmodi/open_data_loader.git}"
BRANCH="${BRANCH:-main}"
SWAP_SIZE_GB="${SWAP_SIZE_GB:-12}"

run_sudo() {
  if [[ "$(id -u)" -eq 0 ]]; then
    "$@"
  elif [[ -n "${SUDO_PASSWORD:-}" ]]; then
    printf '%s\n' "$SUDO_PASSWORD" | sudo -S "$@"
  else
    sudo "$@"
  fi
}

install_packages() {
  run_sudo apt-get update
  run_sudo apt-get install -y ca-certificates curl git openssl
  configure_swap

  if ! command -v docker >/dev/null 2>&1; then
    local docker_installer
    docker_installer="$(mktemp)"
    curl -fsSL https://get.docker.com -o "$docker_installer"
    run_sudo sh "$docker_installer"
    rm -f "$docker_installer"
  fi

  run_sudo systemctl enable --now docker

  if ! command -v ollama >/dev/null 2>&1; then
    local ollama_installer
    ollama_installer="$(mktemp)"
    curl -fsSL https://ollama.com/install.sh -o "$ollama_installer"
    run_sudo sh "$ollama_installer"
    rm -f "$ollama_installer"
  fi

  configure_ollama_service
}

configure_swap() {
  if [[ "$SWAP_SIZE_GB" == "0" ]] || swapon --show=NAME --noheadings | grep -q "^/swapfile$"; then
    return
  fi

  if [[ ! -f /swapfile ]]; then
    run_sudo fallocate -l "${SWAP_SIZE_GB}G" /swapfile
    run_sudo chmod 600 /swapfile
    run_sudo mkswap /swapfile
  fi

  run_sudo swapon /swapfile || true
  if ! grep -qE '^[^#[:space:]]+[[:space:]]+none[[:space:]]+swap[[:space:]]' /etc/fstab; then
    echo "/swapfile none swap sw 0 0" | run_sudo tee -a /etc/fstab >/dev/null
  fi
}

configure_ollama_service() {
  run_sudo mkdir -p /etc/systemd/system/ollama.service.d
  local override_file="/tmp/ollama-openloader-override.conf"
  cat > "$override_file" <<EOF
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
EOF
  run_sudo mv "$override_file" /etc/systemd/system/ollama.service.d/openloader.conf
  run_sudo systemctl daemon-reload
  run_sudo systemctl enable --now ollama
  run_sudo systemctl restart ollama
}

install_gemma_model() {
  local model="${OLLAMA_MODEL:-gemma4:e4b}"

  for _ in {1..30}; do
    if ollama list >/dev/null 2>&1; then
      break
    fi
    sleep 2
  done

  if ! ollama list | awk 'NR > 1 {print $1}' | grep -qx "$model"; then
    ollama pull "$model"
  fi
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
  run_sudo docker compose up -d --build
}

install_packages
install_gemma_model
sync_repo
write_env
start_app

echo "Open Data Loader is running on http://$(hostname -I | awk '{print $1}')/"
