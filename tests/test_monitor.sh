#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DATA_DIR="$PROJECT_ROOT/data"
VERSION_FILE="$DATA_DIR/cortex_code_cli_version"

PASS=0
FAIL=0

assert_eq() {
  local label="$1" expected="$2" actual="$3"
  if [ "$expected" = "$actual" ]; then
    echo "  ✓ $label"
    PASS=$((PASS + 1))
  else
    echo "  ✗ $label (expected='$expected', got='$actual')"
    FAIL=$((FAIL + 1))
  fi
}

echo "=== Cortex Version Monitor - CI Test ==="
echo ""

echo "[1] Testing version extraction"
CURRENT=$(cortex --version | awk '{print $NF}' | sed 's/^v//')
assert_eq "CURRENT is not empty" "1" "$([ -n "$CURRENT" ] && echo 1 || echo 0)"
assert_eq "CURRENT matches semver pattern" "1" "$(echo "$CURRENT" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+' && echo 1 || echo 0)"
echo "  → CURRENT=$CURRENT"
echo ""

echo "[2] Testing stored version read"
ORIGINAL_STORED=$(cat "$VERSION_FILE" | tr -d '[:space:]')
assert_eq "STORED is not empty" "1" "$([ -n "$ORIGINAL_STORED" ] && echo 1 || echo 0)"
echo "  → STORED=$ORIGINAL_STORED"
echo ""

echo "[3] Testing change detection (forced mismatch)"
echo "0.0.0" > "$VERSION_FILE"
STORED=$(cat "$VERSION_FILE" | tr -d '[:space:]')
if [ "$CURRENT" != "$STORED" ]; then
  CHANGED="true"
else
  CHANGED="false"
fi
assert_eq "Detects version change" "true" "$CHANGED"
echo ""

echo "[4] Testing no-change detection (same version)"
echo "$CURRENT" > "$VERSION_FILE"
STORED=$(cat "$VERSION_FILE" | tr -d '[:space:]')
if [ "$CURRENT" != "$STORED" ]; then
  CHANGED="true"
else
  CHANGED="false"
fi
assert_eq "No change when versions match" "false" "$CHANGED"
echo ""

echo "[5] Testing version file write"
echo "0.0.0" > "$VERSION_FILE"
STORED=$(cat "$VERSION_FILE" | tr -d '[:space:]')
if [ "$CURRENT" != "$STORED" ]; then
  echo "$CURRENT" > "$VERSION_FILE"
fi
UPDATED=$(cat "$VERSION_FILE" | tr -d '[:space:]')
assert_eq "Version file updated to current" "$CURRENT" "$UPDATED"
echo ""

# Restore original value
echo "$ORIGINAL_STORED" > "$VERSION_FILE"

echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
