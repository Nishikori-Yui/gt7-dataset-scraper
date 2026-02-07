#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT_DIR="${ROOT_DIR}/local/bin"
mkdir -p "${OUT_DIR}"

cd "${ROOT_DIR}/engines/gt7_hero_check_rust"
cargo build --release
cp target/release/gt7-hero-check "${OUT_DIR}/"
echo "built: ${OUT_DIR}/gt7-hero-check"
