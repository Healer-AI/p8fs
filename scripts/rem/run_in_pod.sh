#!/bin/bash
# Helper script to run REM tests inside a Kubernetes pod

set -e

NAMESPACE="${NAMESPACE:-p8fs}"
POD_NAME="${POD_NAME:-}"
SCRIPT="${SCRIPT:-scripts/rem/test_tidb_rem_comprehensive.py}"
CATEGORY="${CATEGORY:-all}"

# Function to find a suitable pod
find_pod() {
    # Try to find p8fs-api pod first
    POD=$(kubectl get pods -n "$NAMESPACE" -l app=p8fs-api -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

    if [ -z "$POD" ]; then
        # Try storage-worker-medium
        POD=$(kubectl get pods -n "$NAMESPACE" -l app=storage-worker-medium -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    fi

    if [ -z "$POD" ]; then
        # Try storage-worker-small
        POD=$(kubectl get pods -n "$NAMESPACE" -l app=storage-worker-small -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    fi

    if [ -z "$POD" ]; then
        echo "Error: No suitable pod found in namespace $NAMESPACE"
        echo "Tried: p8fs-api, storage-worker-medium, storage-worker-small"
        exit 1
    fi

    echo "$POD"
}

# Get pod name if not specified
if [ -z "$POD_NAME" ]; then
    POD_NAME=$(find_pod)
    echo "Using pod: $POD_NAME"
fi

# Check if pod exists
if ! kubectl get pod "$POD_NAME" -n "$NAMESPACE" >/dev/null 2>&1; then
    echo "Error: Pod $POD_NAME not found in namespace $NAMESPACE"
    exit 1
fi

echo "Running REM tests in pod $POD_NAME (namespace: $NAMESPACE)"
echo "Test category: $CATEGORY"
echo ""

# Run the test script
kubectl exec -n "$NAMESPACE" "$POD_NAME" -- \
    python "$SCRIPT" --category "$CATEGORY"

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo ""
    echo "✓ All tests passed!"
else
    echo ""
    echo "✗ Some tests failed (exit code: $EXIT_CODE)"
fi

exit $EXIT_CODE
