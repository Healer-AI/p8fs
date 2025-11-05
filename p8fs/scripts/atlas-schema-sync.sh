#!/bin/bash
# Atlas schema sync tool for P8FS

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
DB_HOST="${P8FS_PG_HOST:-localhost}"
DB_PORT="${P8FS_PG_PORT:-5438}"
DB_NAME="${P8FS_PG_DATABASE:-app}"
DB_USER="${P8FS_PG_USER:-postgres}"
DB_PASS="${P8FS_PG_PASSWORD:-postgres}"
ACTION="diff"
AUTO_APPROVE=false

# Usage function
usage() {
    echo -e "${BLUE}Usage: $0 [OPTIONS]${NC}"
    echo ""
    echo "Options:"
    echo "  -a, --action ACTION    Action to perform: diff, apply, inspect (default: diff)"
    echo "  -y, --yes              Auto-approve changes (for apply action)"
    echo "  -h, --host HOST        Database host (default: $DB_HOST)"
    echo "  -p, --port PORT        Database port (default: $DB_PORT)"
    echo "  -d, --database DB      Database name (default: $DB_NAME)"
    echo "  -u, --user USER        Database user (default: $DB_USER)"
    echo "  --help                 Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                     # Show diff between current and target schema"
    echo "  $0 --action apply      # Apply schema changes (with confirmation)"
    echo "  $0 --action apply -y   # Apply schema changes automatically"
    echo "  $0 --action inspect    # Inspect current database schema"
    exit 0
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -a|--action)
            ACTION="$2"
            shift 2
            ;;
        -y|--yes)
            AUTO_APPROVE=true
            shift
            ;;
        -h|--host)
            DB_HOST="$2"
            shift 2
            ;;
        -p|--port)
            DB_PORT="$2"
            shift 2
            ;;
        -d|--database)
            DB_NAME="$2"
            shift 2
            ;;
        -u|--user)
            DB_USER="$2"
            shift 2
            ;;
        --help)
            usage
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            usage
            ;;
    esac
done

echo -e "${GREEN}=== P8FS Atlas Schema Manager ===${NC}"

# Check if Atlas is installed
if ! command -v atlas &> /dev/null; then
    echo -e "${RED}Atlas is not installed.${NC}"
    echo "Install it with:"
    echo "  brew install ariga/tap/atlas"
    echo "  or"
    echo "  curl -sSf https://atlasgo.sh | sh"
    exit 1
fi

# Build database URLs
DB_URL="postgres://${DB_USER}:${DB_PASS}@${DB_HOST}:${DB_PORT}/${DB_NAME}?sslmode=disable"
DEV_DB_URL="postgres://${DB_USER}:${DB_PASS}@${DB_HOST}:${DB_PORT}/atlas_dev?sslmode=disable"

# Check database connection
echo -e "${YELLOW}Checking database connection...${NC}"
if ! psql "$DB_URL" -c "SELECT 1;" &> /dev/null; then
    echo -e "${RED}Cannot connect to database${NC}"
    echo "URL: $DB_URL"
    exit 1
fi
echo -e "${GREEN}Connected to database${NC}"

# Find project root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

# Find and combine SQL schema files
echo -e "\n${YELLOW}Collecting schema files...${NC}"
TARGET_SCHEMA="/tmp/p8fs-target-schema.sql"
> "$TARGET_SCHEMA"  # Clear file

# Look for SQL files in various locations
SQL_DIRS=(
    "extensions/sql"
    "extensions/migrations/postgres"
    "migrations"
    "schema"
    "sql"
)

FOUND_FILES=false
for dir in "${SQL_DIRS[@]}"; do
    if [ -d "$dir" ]; then
        for sql_file in "$dir"/*.sql; do
            if [ -f "$sql_file" ]; then
                echo -e "  Found: $sql_file"
                echo -e "\n-- Source: $sql_file" >> "$TARGET_SCHEMA"
                cat "$sql_file" >> "$TARGET_SCHEMA"
                echo "" >> "$TARGET_SCHEMA"
                FOUND_FILES=true
            fi
        done
    fi
done

if [ "$FOUND_FILES" = false ]; then
    echo -e "${YELLOW}No SQL schema files found. Using current database as target.${NC}"
    ACTION="inspect"
fi

# Create dev database if needed
if [ "$ACTION" != "inspect" ]; then
    echo -e "\n${YELLOW}Setting up dev database...${NC}"
    psql "postgres://${DB_USER}:${DB_PASS}@${DB_HOST}:${DB_PORT}/postgres?sslmode=disable" \
        -c "DROP DATABASE IF EXISTS atlas_dev;" 2>/dev/null || true
    psql "postgres://${DB_USER}:${DB_PASS}@${DB_HOST}:${DB_PORT}/postgres?sslmode=disable" \
        -c "CREATE DATABASE atlas_dev;" 2>/dev/null || true
fi

# Perform requested action
case $ACTION in
    inspect)
        echo -e "\n${BLUE}Current Database Schema:${NC}"
        atlas schema inspect --url "$DB_URL" | head -100
        echo -e "\n... (truncated, showing first 100 lines)"
        ;;
        
    diff)
        echo -e "\n${BLUE}Schema Differences:${NC}"
        if atlas schema diff \
            --from "$DB_URL" \
            --to "file://$TARGET_SCHEMA" \
            --dev-url "$DEV_DB_URL" 2>/dev/null; then
            echo -e "\n${GREEN}Diff completed${NC}"
        else
            echo -e "${YELLOW}No differences found or could not compute diff${NC}"
        fi
        ;;
        
    apply)
        echo -e "\n${BLUE}Planned Changes:${NC}"
        
        # First show the diff
        DIFF_OUTPUT=$(atlas schema diff \
            --from "$DB_URL" \
            --to "file://$TARGET_SCHEMA" \
            --dev-url "$DEV_DB_URL" 2>/dev/null || echo "")
            
        if [ -z "$DIFF_OUTPUT" ]; then
            echo -e "${GREEN}No changes needed - schema is up to date!${NC}"
            exit 0
        fi
        
        echo "$DIFF_OUTPUT"
        
        # Ask for confirmation if not auto-approved
        if [ "$AUTO_APPROVE" = false ]; then
            echo -e "\n${YELLOW}Do you want to apply these changes? (yes/no)${NC}"
            read -r response
            if [[ ! "$response" =~ ^[Yy][Ee][Ss]$ ]]; then
                echo -e "${YELLOW}Aborted${NC}"
                exit 0
            fi
        fi
        
        echo -e "\n${YELLOW}Applying schema changes...${NC}"
        if atlas schema apply \
            --url "$DB_URL" \
            --to "file://$TARGET_SCHEMA" \
            --dev-url "$DEV_DB_URL" \
            --auto-approve; then
            echo -e "${GREEN}Schema updated successfully!${NC}"
        else
            echo -e "${RED}Failed to apply schema changes${NC}"
            exit 1
        fi
        ;;
        
    *)
        echo -e "${RED}Unknown action: $ACTION${NC}"
        usage
        ;;
esac

# Cleanup
if [ "$ACTION" != "inspect" ]; then
    echo -e "\n${YELLOW}Cleaning up...${NC}"
    psql "postgres://${DB_USER}:${DB_PASS}@${DB_HOST}:${DB_PORT}/postgres?sslmode=disable" \
        -c "DROP DATABASE IF EXISTS atlas_dev;" 2>/dev/null || true
fi

echo -e "\n${GREEN}Done!${NC}"