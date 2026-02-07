#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="${ROOT_DIR}/dist"
FLAVOR="lite"
RUNTIME=""
SKIP_BUILD=0

usage() {
  cat <<'EOF'
Usage: scripts/package_gt7db.sh [options]

Options:
  --flavor <lite|full>   Package flavor (default: lite)
  --runtime <rid>        Dotnet runtime id (default: auto detect)
  --skip-build           Skip build step, package existing artifacts
  --dist-dir <path>      Output dist directory (default: ./dist)
  -h, --help             Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --flavor)
      FLAVOR="${2:-}"
      shift 2
      ;;
    --runtime)
      RUNTIME="${2:-}"
      shift 2
      ;;
    --skip-build)
      SKIP_BUILD=1
      shift
      ;;
    --dist-dir)
      DIST_DIR="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

if [[ "${FLAVOR}" != "lite" && "${FLAVOR}" != "full" ]]; then
  echo "Invalid --flavor: ${FLAVOR}" >&2
  exit 1
fi

detect_runtime() {
  local os arch
  os="$(uname -s | tr '[:upper:]' '[:lower:]')"
  arch="$(uname -m)"
  case "${os}" in
    darwin) echo "osx-${arch}" ;;
    linux) echo "linux-${arch}" ;;
    *) echo "unsupported" ;;
  esac
}

if [[ -z "${RUNTIME}" ]]; then
  RUNTIME="$(detect_runtime)"
fi

if [[ "${RUNTIME}" == "unsupported" ]]; then
  echo "Unsupported OS for runtime auto-detection" >&2
  exit 1
fi

runtime_to_tokens() {
  local runtime="$1"
  local os="${runtime%%-*}"
  local arch="${runtime##*-}"
  local os_name
  local arch_name
  case "${os}" in
    osx) os_name="macOS" ;;
    linux) os_name="linux" ;;
    win) os_name="windows" ;;
    *) os_name="${os}" ;;
  esac
  case "${arch}" in
    x64|amd64) arch_name="AMD64" ;;
    arm64) arch_name="ARM64" ;;
    *) arch_name="${arch^^}" ;;
  esac
  echo "${os_name} ${arch_name}"
}

if [[ "${SKIP_BUILD}" -eq 0 ]]; then
  "${ROOT_DIR}/scripts/bootstrap_hybrid_env.sh" --skip-playwright-browser
  if command -v dotnet >/dev/null 2>&1; then
    "${ROOT_DIR}/engines/gt7db_launcher_dotnet/build.sh" "${RUNTIME}"
  else
    echo "[package][warn] dotnet not found; gt7db launcher won't be bundled" >&2
  fi
fi

read -r OS_NAME ARCH_NAME < <(runtime_to_tokens "${RUNTIME}")
PKG_NAME="GT7DB_${FLAVOR^^}_${OS_NAME}_${ARCH_NAME}"
PKG_ROOT="${DIST_DIR}/${PKG_NAME}"
rm -rf "${PKG_ROOT}"
mkdir -p "${PKG_ROOT}"
mkdir -p "${PKG_ROOT}/app"
mkdir -p "${PKG_ROOT}/local/bin"
mkdir -p "${PKG_ROOT}/app/scripts"

cp -R "${ROOT_DIR}/gt7_scraper" "${PKG_ROOT}/app/"
cp -R "${ROOT_DIR}/gt7_query" "${PKG_ROOT}/app/"
cp "${ROOT_DIR}/scripts/build_dbs.py" "${PKG_ROOT}/app/scripts/"
cp "${ROOT_DIR}/requirements.txt" "${PKG_ROOT}/app/"
cp "${ROOT_DIR}/README.md" "${PKG_ROOT}/"
cp "${ROOT_DIR}/LICENSE" "${PKG_ROOT}/"

for bin in gt7-downloader gt7-spec-normalizer gt7-db-merge gt7-db-merge-go gt7-hero-check gt7-query-go gt7db; do
  if [[ -f "${ROOT_DIR}/local/bin/${bin}" ]]; then
    cp "${ROOT_DIR}/local/bin/${bin}" "${PKG_ROOT}/local/bin/"
  fi
done

if [[ "${FLAVOR}" == "full" ]]; then
  mkdir -p "${PKG_ROOT}/engines/gt7_playwright"
  cp -R "${ROOT_DIR}/engines/gt7_playwright/dist" "${PKG_ROOT}/engines/gt7_playwright/" 2>/dev/null || true
  cp "${ROOT_DIR}/engines/gt7_playwright/package.json" "${PKG_ROOT}/engines/gt7_playwright/" 2>/dev/null || true
  cp "${ROOT_DIR}/engines/gt7_playwright/package-lock.json" "${PKG_ROOT}/engines/gt7_playwright/" 2>/dev/null || true
fi

cat > "${PKG_ROOT}/run.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export GT7DB_ROOT="${ROOT}/app"
if [[ -x "${ROOT}/local/bin/gt7db" ]]; then
  exec "${ROOT}/local/bin/gt7db" "$@"
fi
if [[ -x "${ROOT}/app/.venv/bin/python" ]]; then
  exec "${ROOT}/app/.venv/bin/python" -m gt7_scraper "$@"
fi
echo "gt7db launcher missing. Build with dotnet or use local Python entrypoints." >&2
exit 2
EOF
chmod +x "${PKG_ROOT}/run.sh"

mkdir -p "${DIST_DIR}"
tar -C "${DIST_DIR}" -czf "${DIST_DIR}/${PKG_NAME}.tar.gz" "${PKG_NAME}"
echo "package created: ${DIST_DIR}/${PKG_NAME}.tar.gz"
