#!/usr/bin/env bash
set -euo pipefail

# ───────────────────────────────
# Usage:
#   ./find_latest_tag_ci.sh [VARIANT] [SUFFIX] [VERSION] [PLATFORM]
# Example:
#   ./find_latest_tag_ci.sh light -light 1.1.7 amd64
#   ./find_latest_tag_ci.sh heavy -heavy 1.1.7 arm64
#
# Required:
#   export GITHUB_TOKEN="ghp_...."
# ───────────────────────────────

OWNER="Percolation-Labs"
PACKAGE_NAME="p8fs-ecosystem-test"

VARIANT="${1:-light}"       # 'light' or 'heavy'
SUFFIX="${2:--light}"       # '-light' or '-heavy'
VERSION="${3:-1.1.7}"       # version to match (can be passed dynamically)
PLATFORM="${4:-amd64}"      # platform (amd64, arm64)
# ───────────────────────────────

find_latest_tag() {
  local variant=$1
  local suffix=$2

  echo "🔍 Searching for ${variant} images with version v${VERSION}..." >&2
  echo "📡 Calling GitHub API..." >&2

  local response
  response=$(curl -s -w "\n%{http_code}" \
    -H "Authorization: Bearer ${GITHUB_TOKEN}" \
    -H "Accept: application/vnd.github+json" \
    "https://api.github.com/orgs/${OWNER}/packages/container/${PACKAGE_NAME}/versions?per_page=100")

  local http_code
  http_code=$(echo "$response" | tail -n1)
  local versions
  versions=$(echo "$response" | head -n -1)

  echo "📊 API Response Code: ${http_code}" >&2
  if [[ "$http_code" != "200" ]]; then
    echo "⚠️  API call failed with code ${http_code}" >&2
    echo "$versions" | head -c 500 >&2
    return 1
  fi

  local tags
  tags=$(echo "$versions" | jq -r '.[].metadata.container.tags[]?' 2>/dev/null | sort -u || true)
  if [[ -z "$tags" ]]; then
    echo "❌ No tags found in API response" >&2
    return 1
  fi

  echo "🔍 Filtering for *-build.*-v${VERSION}-*${suffix}-${PLATFORM}" >&2
  local matching_tags
  matching_tags=$(echo "$tags" | grep -E ".*-build\.[0-9]+-v${VERSION}-.*${suffix}-${PLATFORM}$" || true)

  if [[ -z "$matching_tags" ]]; then
    echo "❌ No matches for ${variant} ${PLATFORM} v${VERSION}" >&2
    return 1
  fi

  local latest_tag=""
  local latest_build_num=0
  while IFS= read -r tag; do
    [[ -z "$tag" ]] && continue
    local build_num
    build_num=$(echo "$tag" | sed -E 's/.*build\.([0-9]+).*/\1/' || echo "0")
    echo "🔢 ${tag} → Build #${build_num}" >&2
    if (( build_num > latest_build_num )); then
      latest_build_num=$build_num
      latest_tag=$tag
    fi
  done <<< "$matching_tags"

  if [[ -n "$latest_tag" ]]; then
    echo "✅ Latest: ${latest_tag}" >&2
    echo "$latest_tag"
  else
    echo "❌ Could not determine latest tag" >&2
    return 1
  fi
}

# ───────────────────────────────
# Execute
# ───────────────────────────────
result=$(find_latest_tag "${VARIANT}" "${SUFFIX}" || echo "")
rc=$?

echo "──────────────────────────────"
if [[ $rc -eq 0 && -n "$result" ]]; then
  latest_tag=$(echo "$result" | head -n1)
  echo "✅ Latest tag for ${VARIANT}-${PLATFORM}: ${latest_tag}"

  if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
    safe_key=$(echo "${VARIANT}_${PLATFORM}" | tr '/-' '__')
    echo "latest_tag=$latest_tag" >> "$GITHUB_OUTPUT"
    echo "image_${safe_key}=$latest_tag" >> "$GITHUB_OUTPUT"
    echo "📝 Stored output: image_${safe_key}"
  fi
else
  echo "❌ find_latest_tag failed (exit code $rc)"
  exit $rc
fi
echo "──────────────────────────────"