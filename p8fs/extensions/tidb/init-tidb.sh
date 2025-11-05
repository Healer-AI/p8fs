#!/bin/bash
# TiDB initialization script
# Runs migrations on container startup

set -e

echo "===================================================================================="
echo "P8FS TiDB Initialization"
echo "===================================================================================="

# Wait for TiDB to be ready
echo "⏳ Waiting for TiDB to be ready..."
for i in {1..30}; do
    if mysql -h localhost -P 4000 -u root -e "SELECT 1" >/dev/null 2>&1; then
        echo "✅ TiDB is ready"
        break
    fi
    echo "   Attempt $i/30: TiDB not ready yet..."
    sleep 2
done

# Run migration
MIGRATION_FILE="/docker-entrypoint-initdb.d/install.sql"

if [ -f "$MIGRATION_FILE" ]; then
    echo "📋 Running migration: $MIGRATION_FILE"
    mysql -h localhost -P 4000 -u root < "$MIGRATION_FILE"

    if [ $? -eq 0 ]; then
        echo "✅ Migration completed successfully"
    else
        echo "❌ Migration failed"
        exit 1
    fi
else
    echo "⚠️  Migration file not found: $MIGRATION_FILE"
    echo "   Skipping initialization"
fi

# Verify tables were created
echo ""
echo "📊 Verifying tables in 'public' database:"
mysql -h localhost -P 4000 -u root -D public -e "SHOW TABLES;" 2>/dev/null || echo "⚠️  Could not show tables"

echo ""
echo "===================================================================================="
echo "✅ TiDB Initialization Complete"
echo "===================================================================================="
echo "Connection: mysql://root@localhost:4000/public"
echo "===================================================================================="
