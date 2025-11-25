#!/bin/bash
#
# Quick script to run dreaming integration tests in sequence
#
# Usage:
#   ./run_dreaming_tests.sh              # Run all tests
#   ./run_dreaming_tests.sh 1            # Run only Test 1
#   ./run_dreaming_tests.sh 1 2          # Run Tests 1 and 2
#

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}=====================================================================${NC}"
echo -e "${BLUE}P8FS Dreaming Integration Tests${NC}"
echo -e "${BLUE}=====================================================================${NC}"
echo ""

# Check PostgreSQL is running
echo -e "${BLUE}Checking PostgreSQL...${NC}"
if ! docker ps | grep -q percolate; then
    echo -e "${RED}❌ PostgreSQL not running${NC}"
    echo "Starting PostgreSQL..."
    docker compose up postgres -d
    echo "Waiting for PostgreSQL to be ready..."
    sleep 5
fi
echo -e "${GREEN}✓ PostgreSQL running${NC}"
echo ""

# Check environment
echo -e "${BLUE}Checking environment...${NC}"
export P8FS_STORAGE_PROVIDER=postgresql

if [ -z "$OPENAI_API_KEY" ]; then
    echo -e "${RED}⚠️  OPENAI_API_KEY not set (required for LLM tests)${NC}"
    echo "LLM tests (Test 3+) will be skipped"
else
    echo -e "${GREEN}✓ OpenAI API key configured${NC}"
    # Use gpt-4o-mini by default for testing
    export OPENAI_MODEL=${OPENAI_MODEL:-gpt-4o-mini}
    echo "  Using model: $OPENAI_MODEL"
fi
echo ""

# Determine which tests to run
if [ $# -eq 0 ]; then
    # Run all tests
    TESTS=(1 2 3)
else
    # Run specified tests
    TESTS=("$@")
fi

echo -e "${BLUE}Running tests: ${TESTS[*]}${NC}"
echo ""

# Run tests
FAILED=0

for TEST_NUM in "${TESTS[@]}"; do
    case $TEST_NUM in
        1)
            echo -e "${BLUE}=====================================================================${NC}"
            echo -e "${BLUE}TEST 1: Database Operations (No LLM)${NC}"
            echo -e "${BLUE}=====================================================================${NC}"
            if uv run pytest tests/integration/test_01_database_operations.py -v -s; then
                echo -e "${GREEN}✓ Test 1 passed${NC}"
            else
                echo -e "${RED}✗ Test 1 failed${NC}"
                FAILED=1
            fi
            echo ""
            ;;
        2)
            echo -e "${BLUE}=====================================================================${NC}"
            echo -e "${BLUE}TEST 2: Resource Affinity (No LLM)${NC}"
            echo -e "${BLUE}=====================================================================${NC}"
            if uv run pytest tests/integration/test_02_resource_affinity.py -v -s; then
                echo -e "${GREEN}✓ Test 2 passed${NC}"
            else
                echo -e "${RED}✗ Test 2 failed${NC}"
                FAILED=1
            fi
            echo ""
            ;;
        3)
            if [ -z "$OPENAI_API_KEY" ]; then
                echo -e "${RED}Skipping Test 3: OpenAI API key required${NC}"
                echo ""
            else
                echo -e "${BLUE}=====================================================================${NC}"
                echo -e "${BLUE}TEST 3: Entity Extraction (LLM Required)${NC}"
                echo -e "${BLUE}=====================================================================${NC}"
                if uv run pytest tests/integration/test_03_entity_extraction.py -v -s; then
                    echo -e "${GREEN}✓ Test 3 passed${NC}"
                else
                    echo -e "${RED}✗ Test 3 failed${NC}"
                    FAILED=1
                fi
                echo ""
            fi
            ;;
        *)
            echo -e "${RED}Unknown test: $TEST_NUM${NC}"
            echo "Valid tests: 1, 2, 3"
            exit 1
            ;;
    esac
done

# Summary
echo -e "${BLUE}=====================================================================${NC}"
if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ All tests passed!${NC}"
else
    echo -e "${RED}✗ Some tests failed${NC}"
    exit 1
fi
echo -e "${BLUE}=====================================================================${NC}"
