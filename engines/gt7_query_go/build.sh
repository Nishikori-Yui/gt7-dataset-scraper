#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT_DIR="${ROOT_DIR}/local/bin"
mkdir -p "${OUT_DIR}"

cd "${ROOT_DIR}/engines/gt7_query_go"
go build -o "${OUT_DIR}/gt7-query-go" .
echo "built: ${OUT_DIR}/gt7-query-go"
