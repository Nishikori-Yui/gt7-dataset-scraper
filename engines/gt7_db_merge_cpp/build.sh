#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT_BIN="${ROOT_DIR}/local/bin/gt7-db-merge"

mkdir -p "${ROOT_DIR}/local/bin"

COMPILER="${CXX:-}"
if [[ -z "${COMPILER}" ]]; then
  if command -v c++ >/dev/null 2>&1; then
    COMPILER="c++"
  elif command -v g++ >/dev/null 2>&1; then
    COMPILER="g++"
  elif command -v clang++ >/dev/null 2>&1; then
    COMPILER="clang++"
  else
    echo "no C++ compiler found" >&2
    exit 2
  fi
fi

"${COMPILER}" -O2 -std=c++17 "${ROOT_DIR}/engines/gt7_db_merge_cpp/main.cpp" -lsqlite3 -o "${OUT_BIN}"
chmod +x "${OUT_BIN}"
echo "built ${OUT_BIN}"
