#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
BUILD_GO=0
INSTALL_PLAYWRIGHT=0
INSTALL_BROWSER=0

usage() {
  cat <<'EOF'
Usage: scripts/bootstrap.sh [options]

Options:
  --python-bin PATH           Python executable (default: python3)
  --build-go                  Build the optional Go parser and image downloader
  --with-playwright           Install the optional Python Playwright package
  --with-playwright-browser    Also install Chromium for Playwright
  -h, --help                   Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --python-bin)
      [[ $# -ge 2 ]] || { echo "--python-bin requires a path" >&2; exit 2; }
      PYTHON_BIN="$2"
      shift 2
      ;;
    --build-go)
      BUILD_GO=1
      shift
      ;;
    --with-playwright)
      INSTALL_PLAYWRIGHT=1
      shift
      ;;
    --with-playwright-browser)
      INSTALL_PLAYWRIGHT=1
      INSTALL_BROWSER=1
      shift
      ;;
    -h|--help)
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

command -v "${PYTHON_BIN}" >/dev/null 2>&1 || { echo "Python not found: ${PYTHON_BIN}" >&2; exit 1; }
cd "${ROOT_DIR}"
"${PYTHON_BIN}" -m venv .venv
"${ROOT_DIR}/.venv/bin/python" -m pip install -r requirements.txt

if [[ "${INSTALL_PLAYWRIGHT}" -eq 1 ]]; then
  "${ROOT_DIR}/.venv/bin/python" -m pip install playwright
  if [[ "${INSTALL_BROWSER}" -eq 1 ]]; then
    "${ROOT_DIR}/.venv/bin/python" -m playwright install chromium
  fi
fi

if [[ "${BUILD_GO}" -eq 1 ]]; then
  command -v go >/dev/null 2>&1 || { echo "Go is required for --build-go" >&2; exit 1; }
  mkdir -p local/bin
  (cd engines/gt7_catalog_go && go build -o ../../local/bin/gt7-catalog-go .)
  (cd engines/gt7_downloader && go build -o ../../local/bin/gt7-downloader .)
fi

cat <<'EOF'
Environment ready.

Activate it with:
  source .venv/bin/activate

Run the scraper with:
  python -m gt7_scraper --help
EOF
