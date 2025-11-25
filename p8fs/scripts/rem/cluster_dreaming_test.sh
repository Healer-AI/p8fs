#!/bin/bash
# Cluster Dreaming Test Script
#
# Tests dreaming worker on Kubernetes cluster
#
# Usage:
#   ./scripts/rem/cluster_dreaming_test.sh --tenant dev-tenant-001
#   ./scripts/rem/cluster_dreaming_test.sh --seed-data

set -e

NAMESPACE="default"
TENANT_ID=""
SEED_DATA=false
VERIFY=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --tenant)
            TENANT_ID="$2"
            shift 2
            ;;
        --namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        --seed-data)
            SEED_DATA=true
            shift
            ;;
        --verify)
            VERIFY=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo "==================================================================="
echo "Cluster Dreaming Test"
echo "==================================================================="
echo "Namespace: $NAMESPACE"
echo "Tenant: ${TENANT_ID:-all}"
echo "Seed data: $SEED_DATA"
echo "Verify: $VERIFY"
echo "==================================================================="

# Check cluster connectivity
echo ""
echo "Checking cluster connectivity..."
kubectl cluster-info --namespace=$NAMESPACE || {
    echo "Error: Cannot connect to cluster"
    exit 1
}

# Seed test data if requested
if [ "$SEED_DATA" = true ]; then
    echo ""
    echo "Seeding test data..."
    kubectl run rem-seed-data \
        --namespace=$NAMESPACE \
        --image=p8fs-eco:latest \
        --restart=Never \
        --rm \
        -it \
        -- python scripts/rem/seed_test_data.py --provider tidb --tenants 3

    echo "Waiting for data to be committed..."
    sleep 5
fi

# Run dreaming worker
echo ""
echo "Running dreaming worker..."

if [ -n "$TENANT_ID" ]; then
    # Run for specific tenant
    kubectl run dreaming-worker-test \
        --namespace=$NAMESPACE \
        --image=p8fs-eco:latest \
        --restart=Never \
        --rm \
        -it \
        --env="P8FS_STORAGE_PROVIDER=tidb" \
        -- python scripts/rem/run_dreaming.py \
            --tenant "$TENANT_ID" \
            --mode both \
            --lookback-hours 720 \
            --provider tidb

else
    # Run for all test tenants
    for tenant in "dev-tenant-001" "pm-tenant-002" "research-tenant-003"; do
        echo "Processing tenant: $tenant"
        kubectl run dreaming-worker-$tenant \
            --namespace=$NAMESPACE \
            --image=p8fs-eco:latest \
            --restart=Never \
            --rm \
            -it \
            --env="P8FS_STORAGE_PROVIDER=tidb" \
            -- python scripts/rem/run_dreaming.py \
                --tenant "$tenant" \
                --mode both \
                --lookback-hours 720 \
                --provider tidb
    done
fi

# Verify results if requested
if [ "$VERIFY" = true ]; then
    echo ""
    echo "Verifying results..."

    if [ -n "$TENANT_ID" ]; then
        kubectl run rem-verify \
            --namespace=$NAMESPACE \
            --image=p8fs-eco:latest \
            --restart=Never \
            --rm \
            -it \
            -- python scripts/rem/test_rem_queries.py \
                --tenant "$TENANT_ID" \
                --provider tidb
    else
        kubectl run rem-verify \
            --namespace=$NAMESPACE \
            --image=p8fs-eco:latest \
            --restart=Never \
            --rm \
            -it \
            -- python scripts/rem/test_rem_queries.py \
                --all-tenants \
                --provider tidb
    fi
fi

echo ""
echo "==================================================================="
echo "Cluster dreaming test completed"
echo "==================================================================="
