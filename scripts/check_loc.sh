#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PY_MAX="${PY_MAX:-400}"
GO_MAX="${GO_MAX:-350}"
CPP_MAX="${CPP_MAX:-400}"

fail_count=0

check_files() {
  local label="$1"
  local limit="$2"
  shift 2
  local files=("$@")
  local local_fail=0
  for path in "${files[@]}"; do
    [[ -f "$path" ]] || continue
    local lines
    lines="$(wc -l < "$path" | tr -d ' ')"
    if [[ "$lines" -gt "$limit" ]]; then
      echo "[LOC][$label] $path: $lines > $limit"
      local_fail=1
    fi
  done
  if [[ "$local_fail" -eq 0 ]]; then
    echo "[LOC][$label] OK (limit=$limit)"
  else
    fail_count=$((fail_count + 1))
  fi
}

mapfile -t py_files < <(git ls-files '*.py')
mapfile -t go_files < <(git ls-files '*.go')
mapfile -t cpp_files < <(git ls-files '*.cpp' '*.cc' '*.cxx' '*.hpp' '*.h')

check_files "python" "$PY_MAX" "${py_files[@]}"
check_files "go" "$GO_MAX" "${go_files[@]}"
check_files "cpp" "$CPP_MAX" "${cpp_files[@]}"

if [[ "$fail_count" -gt 0 ]]; then
  echo "[LOC] FAILED with $fail_count group(s) over limit."
  exit 1
fi

echo "[LOC] PASS"
