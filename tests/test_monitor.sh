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

echo "[6] Testing ~/.local/share/cortex directory exists"
CORTEX_DIR="$HOME/.local/share/cortex"
assert_eq "CORTEX_DIR exists" "1" "$([ -d "$CORTEX_DIR" ] && echo 1 || echo 0)"
echo "  → CORTEX_DIR=$CORTEX_DIR"
echo ""

echo "[7] Testing version directories are present"
VERSION_DIR_COUNT=$(find "$CORTEX_DIR" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l | tr -d ' ')
assert_eq "At least one version directory exists" "1" "$([ "$VERSION_DIR_COUNT" -gt 0 ] && echo 1 || echo 0)"
echo "  → Found $VERSION_DIR_COUNT version director(ies)"
echo ""

echo "[8] Testing bundled_skills directory exists in a version folder"
SKILLS_FOUND=false
SKILL_COUNT=0
for dir in $(find "$CORTEX_DIR" -mindepth 1 -maxdepth 1 -type d); do
  if [ -d "$dir/bundled_skills" ]; then
    SKILLS_FOUND=true
    SKILL_COUNT=$(find "$dir/bundled_skills" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l | tr -d ' ')
    break
  fi
done
assert_eq "bundled_skills directory found" "true" "$SKILLS_FOUND"
assert_eq "bundled_skills has at least 1 skill" "1" "$([ "$SKILL_COUNT" -gt 0 ] && echo 1 || echo 0)"
echo "  → Found $SKILL_COUNT bundled skills"
echo ""

echo "[9] Testing current version has a matching local folder"
VERSION_CLEAN=$(echo "$CURRENT" | cut -d'+' -f1)
MATCH_FOUND=false
for dir in $(find "$CORTEX_DIR" -mindepth 1 -maxdepth 1 -type d); do
  DIRNAME=$(basename "$dir")
  if echo "$DIRNAME" | grep -q "^$VERSION_CLEAN"; then
    MATCH_FOUND=true
    break
  fi
done
assert_eq "Local folder matches CLI version $VERSION_CLEAN" "true" "$MATCH_FOUND"
echo ""

# Restore original value
echo "$ORIGINAL_STORED" > "$VERSION_FILE"

echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
