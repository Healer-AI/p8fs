#!/bin/bash
#
# Run save_memory integration test in K8s cluster with TiKV
#
# Usage:
#   ./scripts/run_tikv_test.sh               # Run in existing pod
#   ./scripts/run_tikv_test.sh --job         # Run as K8s job
#   ./scripts/run_tikv_test.sh --local-tidb  # Run locally against cluster TiDB

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# Default values
RUN_MODE="exec"
POD_NAME=""
NAMESPACE="default"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --job)
            RUN_MODE="job"
            shift
            ;;
        --local-tidb)
            RUN_MODE="local"
            shift
            ;;
        --pod)
            POD_NAME="$2"
            shift 2
            ;;
        --namespace|-n)
            NAMESPACE="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --job              Run as K8s job"
            echo "  --local-tidb       Run locally against cluster TiDB (port-forward)"
            echo "  --pod NAME         Exec into specific pod (default: auto-detect)"
            echo "  --namespace NS     K8s namespace (default: default)"
            echo "  --help             Show this help message"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

case $RUN_MODE in
    exec)
        log_info "Running test via kubectl exec into cluster pod..."

        # Auto-detect pod if not specified
        if [ -z "$POD_NAME" ]; then
            log_info "Auto-detecting p8fs pod..."
            POD_NAME=$(kubectl get pods -n "$NAMESPACE" -l app=p8fs -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

            if [ -z "$POD_NAME" ]; then
                log_error "No p8fs pods found in namespace $NAMESPACE"
                log_info "Please specify pod name with --pod option"
                exit 1
            fi

            log_info "Using pod: $POD_NAME"
        fi

        # Copy test script to pod
        log_info "Copying test script to pod..."
        kubectl cp "$SCRIPT_DIR/test_save_memory_tikv.py" \
            "$NAMESPACE/$POD_NAME:/tmp/test_save_memory_tikv.py"

        # Run test in pod
        log_info "Executing test in pod..."
        kubectl exec -n "$NAMESPACE" "$POD_NAME" -- \
            env P8FS_STORAGE_PROVIDER=tidb \
            python3 /tmp/test_save_memory_tikv.py

        log_info "Test completed"
        ;;

    job)
        log_info "Running test as K8s job..."

        # Check if job YAML exists
        JOB_YAML="$PROJECT_ROOT/k8s/jobs/test-save-memory.yaml"
        if [ ! -f "$JOB_YAML" ]; then
            log_error "Job YAML not found: $JOB_YAML"
            exit 1
        fi

        # Delete existing job if present
        kubectl delete job test-save-memory-tikv -n "$NAMESPACE" 2>/dev/null || true

        # Apply job
        log_info "Creating job..."
        kubectl apply -f "$JOB_YAML" -n "$NAMESPACE"

        # Wait for job to complete
        log_info "Waiting for job to complete..."
        kubectl wait --for=condition=complete --timeout=300s \
            job/test-save-memory-tikv -n "$NAMESPACE"

        # Get job pod name
        JOB_POD=$(kubectl get pods -n "$NAMESPACE" \
            -l job-name=test-save-memory-tikv \
            -o jsonpath='{.items[0].metadata.name}')

        # Show logs
        log_info "Job logs:"
        kubectl logs -n "$NAMESPACE" "$JOB_POD"

        # Cleanup
        log_info "Cleaning up job..."
        kubectl delete job test-save-memory-tikv -n "$NAMESPACE"

        log_info "Test completed"
        ;;

    local)
        log_info "Running test locally against cluster TiDB..."

        # Check if TiDB port-forward is running
        if ! nc -z localhost 4000 2>/dev/null; then
            log_warn "TiDB port-forward not detected on localhost:4000"
            log_info "Starting port-forward to TiDB service..."

            # Find TiDB service
            TIDB_SERVICE=$(kubectl get svc -n "$NAMESPACE" -l app=tidb -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

            if [ -z "$TIDB_SERVICE" ]; then
                log_error "TiDB service not found in namespace $NAMESPACE"
                exit 1
            fi

            log_info "Port-forwarding $TIDB_SERVICE..."
            kubectl port-forward -n "$NAMESPACE" "svc/$TIDB_SERVICE" 4000:4000 &
            PF_PID=$!

            # Wait for port-forward to be ready
            sleep 3

            # Ensure cleanup on exit
            trap "kill $PF_PID 2>/dev/null || true" EXIT
        fi

        # Set environment variables
        export P8FS_STORAGE_PROVIDER=tidb
        export P8FS_TIDB_HOST=localhost
        export P8FS_TIDB_PORT=4000
        export P8FS_TIDB_DATABASE=test
        export P8FS_TIDB_USER=root
        export P8FS_DEFAULT_TENANT_ID=tenant-test

        # Check if API keys are set
        if [ -z "$OPENAI_API_KEY" ]; then
            log_warn "OPENAI_API_KEY not set - test may fail on LLM calls"
        fi

        # Run test
        log_info "Running test script..."
        cd "$PROJECT_ROOT"
        uv run python "$SCRIPT_DIR/test_save_memory_tikv.py"

        log_info "Test completed"
        ;;
esac
