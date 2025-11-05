#!/bin/bash
# TiDB Migration Helper Script
#
# This script helps apply migrations to the cluster TiDB database.
# It handles port-forwarding and cleanup automatically.
#
# Usage:
#   # Show databases
#   ./scripts/tidb_migrate.sh --show-databases
#
#   # Show tables
#   ./scripts/tidb_migrate.sh --database public --show-tables
#
#   # Apply migration file
#   ./scripts/tidb_migrate.sh --database public --apply-migration /tmp/migration.sql
#
#   # Generate and apply p8fs models
#   ./scripts/tidb_migrate.sh --generate-and-apply-models

set -e

TIDB_POD="fresh-cluster-tidb-0"
TIDB_NAMESPACE="tikv-cluster"
LOCAL_PORT="4000"

# Color output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}🔄 P8FS TiDB Migration Helper${NC}"
echo

# Check if TiDB pod exists
if ! kubectl get pod -n $TIDB_NAMESPACE $TIDB_POD &> /dev/null; then
    echo -e "${RED}❌ TiDB pod not found: $TIDB_NAMESPACE/$TIDB_POD${NC}"
    echo "Available TiDB pods:"
    kubectl get pods -n $TIDB_NAMESPACE | grep tidb
    exit 1
fi

# Check if port is already in use
if lsof -Pi :$LOCAL_PORT -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    echo -e "${YELLOW}⚠️  Port $LOCAL_PORT is already in use. Checking if it's our port-forward...${NC}"
    PID=$(lsof -Pi :$LOCAL_PORT -sTCP:LISTEN -t)
    if ps -p $PID | grep -q "port-forward"; then
        echo -e "${GREEN}✓ Existing port-forward found, using it${NC}"
        USE_EXISTING=1
    else
        echo -e "${RED}❌ Port $LOCAL_PORT is in use by another process (PID: $PID)${NC}"
        echo "Please free up the port or use a different port"
        exit 1
    fi
else
    USE_EXISTING=0
fi

# Start port-forward if needed
if [ $USE_EXISTING -eq 0 ]; then
    echo -e "${YELLOW}📡 Starting port-forward to TiDB...${NC}"
    kubectl port-forward -n $TIDB_NAMESPACE $TIDB_POD $LOCAL_PORT:4000 &
    PF_PID=$!

    # Wait for port-forward to be ready
    echo -n "Waiting for port-forward"
    for i in {1..30}; do
        if lsof -Pi :$LOCAL_PORT -sTCP:LISTEN -t >/dev/null 2>&1 ; then
            echo " ready!"
            break
        fi
        echo -n "."
        sleep 0.5
    done

    if ! lsof -Pi :$LOCAL_PORT -sTCP:LISTEN -t >/dev/null 2>&1 ; then
        echo -e "\n${RED}❌ Failed to establish port-forward${NC}"
        kill $PF_PID 2>/dev/null || true
        exit 1
    fi

    # Cleanup on exit
    cleanup() {
        echo -e "\n${YELLOW}🧹 Cleaning up port-forward...${NC}"
        kill $PF_PID 2>/dev/null || true
        wait $PF_PID 2>/dev/null || true
        echo -e "${GREEN}✓ Port-forward stopped${NC}"
    }
    trap cleanup EXIT
fi

# Run the Python script with localhost
echo -e "${GREEN}🔧 Executing TiDB operation...${NC}"
echo

cd "$(dirname "$0")/.." || exit 1
uv run python scripts/tidb_query.py --host localhost --port $LOCAL_PORT "$@"

echo
echo -e "${GREEN}✓ Operation complete${NC}"
