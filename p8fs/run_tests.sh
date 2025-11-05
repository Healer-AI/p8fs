#!/bin/bash

# Script to run unit and integration tests

echo "P8FS Core - Test Runner"
echo "======================"

# Function to check if PostgreSQL is ready
wait_for_postgres() {
    echo "Waiting for PostgreSQL to be ready..."
    for i in {1..30}; do
        if pg_isready -h localhost -p 5438 -U postgres 2>/dev/null; then
            echo "PostgreSQL is ready!"
            return 0
        fi
        echo -n "."
        sleep 1
    done
    echo ""
    echo "ERROR: PostgreSQL failed to start"
    return 1
}

# Parse command line arguments
RUN_INTEGRATION=false
RUN_UNIT=true

while [[ $# -gt 0 ]]; do
    case $1 in
        --integration)
            RUN_INTEGRATION=true
            shift
            ;;
        --unit-only)
            RUN_UNIT=true
            RUN_INTEGRATION=false
            shift
            ;;
        --all)
            RUN_UNIT=true
            RUN_INTEGRATION=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--unit-only|--integration|--all]"
            exit 1
            ;;
    esac
done

# Run unit tests
if [ "$RUN_UNIT" = true ]; then
    echo ""
    echo "Running Unit Tests..."
    echo "--------------------"
    uv run pytest tests/unit/ -v --tb=short
    UNIT_EXIT=$?
else
    UNIT_EXIT=0
fi

# Run integration tests
if [ "$RUN_INTEGRATION" = true ]; then
    echo ""
    echo "Setting up Integration Test Environment..."
    echo "-----------------------------------------"
    
    # Start PostgreSQL using default docker-compose
    docker compose up postgres -d
    
    # Wait for services
    wait_for_postgres
    
    if [ $? -eq 0 ]; then
        echo ""
        echo "Running Integration Tests..."
        echo "---------------------------"
        export SKIP_INTEGRATION_TESTS=false
        
        uv run pytest tests/integration/ -v --tb=short -m integration
        INTEGRATION_EXIT=$?
        
        # Optionally verify database state after tests
        if [ -f tests/integration/verify_embeddings.py ]; then
            echo ""
            echo "Verifying Database State..."
            echo "---------------------------"
            uv run python tests/integration/verify_embeddings.py
        fi
    else
        INTEGRATION_EXIT=1
    fi
    
    # Cleanup
    echo ""
    echo "Cleaning up..."
    docker compose down -v
else
    INTEGRATION_EXIT=0
fi

# Exit with appropriate code
if [ $UNIT_EXIT -ne 0 ] || [ $INTEGRATION_EXIT -ne 0 ]; then
    echo ""
    echo "Tests FAILED!"
    exit 1
else
    echo ""
    echo "All tests PASSED!"
    exit 0
fi