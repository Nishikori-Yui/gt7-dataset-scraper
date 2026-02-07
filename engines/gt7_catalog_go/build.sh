#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
OUT_DIR="$REPO_ROOT/local/bin"
mkdir -p "$OUT_DIR"

cd "$SCRIPT_DIR"
go build -o "$OUT_DIR/gt7-catalog-go" .
echo "built: $OUT_DIR/gt7-catalog-go"
