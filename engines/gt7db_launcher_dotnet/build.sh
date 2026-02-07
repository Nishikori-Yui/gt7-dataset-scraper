#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROJ_DIR="${ROOT_DIR}/engines/gt7db_launcher_dotnet"
OUT_DIR="${ROOT_DIR}/local/bin"

RUNTIME="${1:-linux-amd64}"

case "${RUNTIME}" in
  osx-amd64) DOTNET_RUNTIME="osx-x64" ;;
  linux-amd64) DOTNET_RUNTIME="linux-x64" ;;
  win-amd64) DOTNET_RUNTIME="win-x64" ;;
  *) DOTNET_RUNTIME="${RUNTIME}" ;;
esac

dotnet publish "${PROJ_DIR}/Gt7db.Launcher.csproj" \
  -c Release \
  -r "${DOTNET_RUNTIME}" \
  --self-contained true \
  /p:PublishSingleFile=true \
  /p:PublishTrimmed=false \
  -o "${OUT_DIR}/gt7db-${RUNTIME}"

cp "${OUT_DIR}/gt7db-${RUNTIME}/gt7db" "${OUT_DIR}/gt7db" 2>/dev/null || true

echo "published: ${OUT_DIR}/gt7db-${RUNTIME}"
