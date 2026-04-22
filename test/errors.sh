#!/usr/bin/env bash
# Exercise install.sh's preflight error paths without touching real state.
# Each scenario sets up a sandbox env, runs the script, and asserts on the
# exit code.

set -euo pipefail

SCRIPT="$(cd "$(dirname "$0")/.." && pwd)/install.sh"
SANDBOX="$(mktemp -d)"
trap 'rm -rf "$SANDBOX"' EXIT

pass=0
fail=0

assert_exit() {
  local want="$1" got="$2" name="$3"
  if [[ "$got" -eq "$want" ]]; then
    printf '  \033[32mPASS\033[0m %-30s (exit %d)\n' "$name" "$got"
    pass=$((pass+1))
  else
    printf '  \033[31mFAIL\033[0m %-30s (want %d, got %d)\n' "$name" "$want" "$got"
    fail=$((fail+1))
  fi
}

echo "fixture: sandbox=$SANDBOX"
echo

# 1. E_NO_OPENCLAW — empty PATH so `openclaw` is missing.
set +e
env -i PATH="/usr/bin:/bin" HOME="$SANDBOX" bash "$SCRIPT" >/dev/null 2>&1
code=$?
set -e
assert_exit 10 "$code" "E_NO_OPENCLAW"

# 2. E_USAGE — unknown section name.
set +e
"$SCRIPT" apply bogus >/dev/null 2>&1
code=$?
set -e
assert_exit 64 "$code" "E_USAGE (bad section)"

# 3. E_USAGE — missing section name.
set +e
"$SCRIPT" apply >/dev/null 2>&1
code=$?
set -e
assert_exit 64 "$code" "E_USAGE (no section)"

# 4. --help exits 0 cleanly.
set +e
"$SCRIPT" --help >/dev/null
code=$?
set -e
assert_exit 0 "$code" "--help"

echo
echo "summary: ${pass} passed, ${fail} failed"
[[ "$fail" -eq 0 ]]
