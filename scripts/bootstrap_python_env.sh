#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"
PYTHON_BIN="${PYTHON_BIN:-python3}"

INSTALL_PLAYWRIGHT=0
INSTALL_PLAYWRIGHT_BROWSER=0

log() {
  printf '[bootstrap-python] %s\n' "$*"
}

die() {
  printf '[bootstrap-python][error] %s\n' "$*" >&2
  exit 1
}

have_cmd() {
  command -v "$1" >/dev/null 2>&1
}

usage() {
  cat <<'EOF'
Usage: scripts/bootstrap_python_env.sh [options]

Options:
  --with-playwright           Install Playwright Python package
  --with-playwright-browser   Also install Chromium via Playwright
  --python-bin PATH           Python executable (default: python3)
  -h, --help                  Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-playwright)
      INSTALL_PLAYWRIGHT=1
      shift
      ;;
    --with-playwright-browser)
      INSTALL_PLAYWRIGHT=1
      INSTALL_PLAYWRIGHT_BROWSER=1
      shift
      ;;
    --python-bin)
      shift
      [[ $# -gt 0 ]] || die "--python-bin requires a value"
      PYTHON_BIN="$1"
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

main() {
  cd "${ROOT_DIR}"
  have_cmd "${PYTHON_BIN}" || die "Python not found: ${PYTHON_BIN}"

  log "Creating/updating venv at ${VENV_DIR}"
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
  "${VENV_DIR}/bin/python" -m pip install --upgrade pip wheel
  "${VENV_DIR}/bin/pip" install -r "${ROOT_DIR}/requirements.txt"

  if [[ "${INSTALL_PLAYWRIGHT}" -eq 1 ]]; then
    log "Installing Playwright Python package"
    "${VENV_DIR}/bin/pip" install playwright
    if [[ "${INSTALL_PLAYWRIGHT_BROWSER}" -eq 1 ]]; then
      log "Installing Playwright Chromium browser"
      "${VENV_DIR}/bin/python" -m playwright install chromium
    fi
  fi

  log "Environment ready"
  "${VENV_DIR}/bin/python" --version || true
  cat <<'EOF'

Next commands:
  source .venv/bin/activate
  python -m gt7_scraper --engine python --help
  python scripts/build_dbs.py --engine python --help
EOF
}

main "$@"
