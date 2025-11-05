#!/bin/bash
# End-to-end diagnostic using existing CLI commands only
# No code duplication - just orchestrates tested components

set -e  # Exit on error

TENANT_ID="${1:-tenant-test}"
PROVIDER="${P8FS_STORAGE_PROVIDER:-postgresql}"
MODEL="gpt-4.1-mini"

echo "╔════════════════════════════════════════════════════════════╗"
echo "║   Dream & Moment Email Flow Diagnostic                    ║"
echo "║                                                            ║"
echo "║   Provider: $PROVIDER"
echo "║   Tenant: $TENANT_ID"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Step 1: Process sample file → creates resources
echo "▶ Step 1: Process Sample File (creates resources)"
uv run python -m p8fs.cli process tests/sample_data/content/diary_sample.md \
  --tenant-id "$TENANT_ID"
echo "✓ Sample file processed"
echo ""

# Step 2: Extract moments from resources → creates moments
echo "▶ Step 2: First-Order Dreaming (resources → moments)"
uv run python -m p8fs.cli dreaming \
  --tenant-id "$TENANT_ID" \
  --task moments \
  --model "$MODEL"
echo "✓ Moments extracted"
echo ""

# Step 3: Check what scheduled tasks exist
echo "▶ Step 3: List Scheduled Tasks"
uv run python -m p8fs.cli scheduler --list-tasks
echo ""

echo "╔════════════════════════════════════════════════════════════╗"
echo "║   Diagnostic Complete                                      ║"
echo "╚════════════════════════════════════════════════════════════╝"
