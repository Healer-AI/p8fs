#!/bin/bash
set -e

# Check Tenant Activity in SeaweedFS Filer
# This script helps discover and analyze tenant file uploads in SeaweedFS

ENDPOINT="http://localhost:8333"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    cat <<EOF
Usage: $0 [COMMAND] [OPTIONS]

Commands:
  list-tenants           List all tenant buckets
  count-files            Count files per tenant (top 10)
  list-tenant-files      List files for specific tenant
  reprocess-tenant       Reprocess all files for specific tenant

Options:
  --tenant-id TENANT     Tenant ID (required for list-tenant-files and reprocess-tenant)

Prerequisites:
  1. Port-forward SeaweedFS S3:
     kubectl port-forward -n seaweed svc/seaweedfs-s3 8333:8333

  2. Port-forward NATS (for reprocessing):
     kubectl port-forward -n p8fs svc/nats 4222:4222

  3. AWS CLI with S3 credentials configured

Examples:
  # List all tenant buckets
  $0 list-tenants

  # Count files per tenant
  $0 count-files

  # List files in specific tenant
  $0 list-tenant-files --tenant-id tenant-7737c2b1eb7ca1b1c0a0da8a29a836ca

  # Reprocess all files for tenant
  $0 reprocess-tenant --tenant-id tenant-7737c2b1eb7ca1b1c0a0da8a29a836ca
EOF
    exit 1
}

get_s3_credentials() {
    echo "Fetching S3 credentials from Kubernetes secret..." >&2
    kubectl get secret -n seaweed seaweedfs-s3-config \
        -o jsonpath='{.data.seaweedfs_s3_config}' | base64 -d | \
        python3 -c "import sys, json; creds = json.load(sys.stdin)['identities'][0]['credentials'][0]; print(f\"{creds['accessKey']}\n{creds['secretKey']}\")"
}

list_tenants() {
    echo "Listing all tenant buckets..."
    echo ""

    read -r ACCESS_KEY SECRET_KEY < <(get_s3_credentials)

    AWS_ACCESS_KEY_ID="$ACCESS_KEY" \
    AWS_SECRET_ACCESS_KEY="$SECRET_KEY" \
    aws s3 ls --endpoint-url="$ENDPOINT" --no-verify-ssl 2>/dev/null | \
    grep -E "tenant-|test-corp" | awk '{print $3}'
}

count_files() {
    echo "Counting files per tenant bucket (top 10)..."
    echo ""

    read -r ACCESS_KEY SECRET_KEY < <(get_s3_credentials)

    echo "Tenant,File Count"

    AWS_ACCESS_KEY_ID="$ACCESS_KEY" \
    AWS_SECRET_ACCESS_KEY="$SECRET_KEY" \
    aws s3 ls --endpoint-url="$ENDPOINT" --no-verify-ssl 2>/dev/null | \
    awk '{print $3}' | \
    while read bucket; do
        if [[ "$bucket" == tenant-* ]] || [[ "$bucket" == "test-corp" ]]; then
            count=$(AWS_ACCESS_KEY_ID="$ACCESS_KEY" \
                    AWS_SECRET_ACCESS_KEY="$SECRET_KEY" \
                    aws s3 ls "s3://$bucket" --recursive --endpoint-url="$ENDPOINT" --no-verify-ssl 2>/dev/null | wc -l | xargs)
            echo "$bucket,$count"
        fi
    done | sort -t, -k2 -rn | head -10 | column -t -s,
}

list_tenant_files() {
    local tenant_id="$1"

    if [[ -z "$tenant_id" ]]; then
        echo "Error: --tenant-id required" >&2
        usage
    fi

    echo "Listing files for tenant: $tenant_id"
    echo ""

    read -r ACCESS_KEY SECRET_KEY < <(get_s3_credentials)

    AWS_ACCESS_KEY_ID="$ACCESS_KEY" \
    AWS_SECRET_ACCESS_KEY="$SECRET_KEY" \
    aws s3 ls "s3://$tenant_id/" --recursive --endpoint-url="$ENDPOINT" --no-verify-ssl 2>/dev/null
}

reprocess_tenant() {
    local tenant_id="$1"

    if [[ -z "$tenant_id" ]]; then
        echo "Error: --tenant-id required" >&2
        usage
    fi

    echo "Reprocessing all files for tenant: $tenant_id"
    echo ""

    read -r ACCESS_KEY SECRET_KEY < <(get_s3_credentials)

    local file_count=0

    AWS_ACCESS_KEY_ID="$ACCESS_KEY" \
    AWS_SECRET_ACCESS_KEY="$SECRET_KEY" \
    aws s3 ls "s3://$tenant_id/" --recursive --endpoint-url="$ENDPOINT" --no-verify-ssl 2>/dev/null | \
    while read -r date time size file; do
        echo "Reprocessing: $file (size: $size bytes)"

        uv run -p p8fs python -m p8fs.cli retry \
            --uri "$file" \
            --tenant-id "$tenant_id" \
            --size "$size"

        ((file_count++))
        echo ""
    done

    echo "Completed reprocessing for tenant $tenant_id"
}

# Parse arguments
COMMAND="${1:-}"
shift || true

TENANT_ID=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --tenant-id)
            TENANT_ID="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage
            ;;
    esac
done

# Execute command
case "$COMMAND" in
    list-tenants)
        list_tenants
        ;;
    count-files)
        count_files
        ;;
    list-tenant-files)
        list_tenant_files "$TENANT_ID"
        ;;
    reprocess-tenant)
        reprocess_tenant "$TENANT_ID"
        ;;
    *)
        usage
        ;;
esac
