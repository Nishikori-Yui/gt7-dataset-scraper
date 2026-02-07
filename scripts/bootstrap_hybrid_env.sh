#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"
LOCAL_BIN_DIR="${ROOT_DIR}/local/bin"

INSTALL_SYSTEM=1
INSTALL_PLAYWRIGHT_BROWSER=1
BUILD_COMPONENTS=1

log() {
  printf '[bootstrap] %s\n' "$*"
}

warn() {
  printf '[bootstrap][warn] %s\n' "$*" >&2
}

die() {
  printf '[bootstrap][error] %s\n' "$*" >&2
  exit 1
}

have_cmd() {
  command -v "$1" >/dev/null 2>&1
}

usage() {
  cat <<'EOF'
Usage: scripts/bootstrap_hybrid_env.sh [options]

Options:
  --no-system-install         Do not install system packages
  --skip-playwright-browser   Do not run `npx playwright install chromium`
  --skip-build                Do not build Go/Node/Rust components
  -h, --help                  Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-system-install)
      INSTALL_SYSTEM=0
      shift
      ;;
    --skip-playwright-browser)
      INSTALL_PLAYWRIGHT_BROWSER=0
      shift
      ;;
    --skip-build)
      BUILD_COMPONENTS=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "Unknown option: $1"
      ;;
  esac
done

install_macos_deps() {
  have_cmd brew || die "Homebrew is required on macOS: https://brew.sh"
  local packages=(python go node rustup-init)
  local missing=()
  local pkg
  for pkg in "${packages[@]}"; do
    if ! brew list --versions "$pkg" >/dev/null 2>&1; then
      missing+=("$pkg")
    fi
  done
  if [[ ${#missing[@]} -gt 0 ]]; then
    log "Installing macOS packages: ${missing[*]}"
    brew install "${missing[@]}"
  else
    log "macOS packages already installed"
  fi
}

install_linux_deps() {
  have_cmd apt-get || die "Only apt-based Linux is supported by this script"
  log "Installing Linux packages via apt"
  sudo apt-get update
  sudo apt-get install -y python3 python3-venv python3-pip golang-go nodejs npm curl build-essential
}

install_rust_if_missing() {
  if have_cmd cargo; then
    return
  fi
  if have_cmd rustup-init; then
    log "Initializing Rust toolchain via rustup-init"
    rustup-init -y --no-modify-path
  else
    log "Installing Rust toolchain via rustup"
    curl https://sh.rustup.rs -sSf | sh -s -- -y
  fi
}

load_cargo_env_if_present() {
  if [[ -f "${HOME}/.cargo/env" ]]; then
    # shellcheck disable=SC1090
    source "${HOME}/.cargo/env"
  fi
}

setup_python_env() {
  have_cmd python3 || die "python3 not found"
  log "Creating/updating Python venv at ${VENV_DIR}"
  python3 -m venv "${VENV_DIR}"
  "${VENV_DIR}/bin/python" -m pip install --upgrade pip wheel
  "${VENV_DIR}/bin/pip" install -r "${ROOT_DIR}/requirements.txt"
}

build_go_downloader() {
  have_cmd go || die "go not found"
  log "Building Go downloader"
  (
    cd "${ROOT_DIR}/engines/gt7_downloader"
    go build -o "${LOCAL_BIN_DIR}/gt7-downloader" .
  )
}

build_node_worker() {
  have_cmd node || die "node not found"
  have_cmd npm || die "npm not found"
  log "Building Node Playwright worker"
  (
    cd "${ROOT_DIR}/engines/gt7_playwright"
    npm install
    if [[ "${INSTALL_PLAYWRIGHT_BROWSER}" -eq 1 ]]; then
      npx playwright install chromium
    fi
    npm run build
  )
}

create_node_wrapper() {
  local wrapper="${LOCAL_BIN_DIR}/gt7-playwright"
  cat > "${wrapper}" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
node "${ROOT_DIR}/engines/gt7_playwright/dist/cli.js" "$@"
EOF
  chmod +x "${wrapper}"
}

build_rust_normalizer() {
  have_cmd cargo || die "cargo not found"
  log "Building Rust spec normalizer"
  (
    cd "${ROOT_DIR}/engines/gt7_spec_normalizer"
    cargo build --release
    cp "target/release/gt7-spec-normalizer" "${LOCAL_BIN_DIR}/"
  )
}

print_summary() {
  log "Toolchain versions:"
  python3 --version || true
  go version || true
  node --version || true
  npm --version || true
  cargo --version || true
  log "Installed local binaries:"
  ls -la "${LOCAL_BIN_DIR}" || true
  cat <<'EOF'

Next commands:
  source .venv/bin/activate
  python -m gt7_scraper --engine hybrid --help
  python scripts/build_dbs.py --engine hybrid --help
EOF
}

main() {
  cd "${ROOT_DIR}"
  mkdir -p "${LOCAL_BIN_DIR}"

  if [[ "${INSTALL_SYSTEM}" -eq 1 ]]; then
    case "$(uname -s)" in
      Darwin)
        install_macos_deps
        ;;
      Linux)
        install_linux_deps
        ;;
      *)
        die "Unsupported OS: $(uname -s)"
        ;;
    esac
    install_rust_if_missing
  fi

  load_cargo_env_if_present
  setup_python_env

  if [[ "${BUILD_COMPONENTS}" -eq 1 ]]; then
    build_go_downloader
    build_node_worker
    create_node_wrapper
    build_rust_normalizer
  fi

  print_summary
}

main "$@"
