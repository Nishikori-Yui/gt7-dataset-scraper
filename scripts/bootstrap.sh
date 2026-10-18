#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UV_PYTHON_VERSION=""
BUILD_GO=0
INSTALL_PLAYWRIGHT=0
INSTALL_BROWSER=0

usage() {
  cat <<'EOF'
Usage: scripts/bootstrap.sh [options]

Options:
  --python VERSION            Python version for uv (for example 3.12)
  --build-go                  Build the optional Go parser and image downloader
  --with-playwright           Install the optional Python Playwright package
  --with-playwright-browser    Also install Chromium for Playwright
  -h, --help                   Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --python)
      [[ $# -ge 2 ]] || { echo "--python requires a version" >&2; exit 2; }
      UV_PYTHON_VERSION="$2"
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

command -v uv >/dev/null 2>&1 || { echo "uv is required: https://docs.astral.sh/uv/getting-started/installation/" >&2; exit 1; }
cd "${ROOT_DIR}"
SYNC_ARGS=(sync --locked)
if [[ -n "${UV_PYTHON_VERSION}" ]]; then
  SYNC_ARGS+=(--python "${UV_PYTHON_VERSION}")
fi
if [[ "${INSTALL_PLAYWRIGHT}" -eq 1 ]]; then
  SYNC_ARGS+=(--extra browser)
fi
uv "${SYNC_ARGS[@]}"
if [[ "${INSTALL_BROWSER}" -eq 1 ]]; then
  uv run --locked --extra browser python -m playwright install chromium
fi

if [[ "${BUILD_GO}" -eq 1 ]]; then
  command -v go >/dev/null 2>&1 || { echo "Go is required for --build-go" >&2; exit 1; }
  mkdir -p local/bin
  (cd engines/gt7_catalog_go && go build -o ../../local/bin/gt7-catalog-go .)
  (cd engines/gt7_downloader && go build -o ../../local/bin/gt7-downloader .)
fi

cat <<'EOF'
Environment ready.

Run the scraper with:
  uv run python -m gt7_scraper --help

Or activate the environment:
  source .venv/bin/activate
EOF
