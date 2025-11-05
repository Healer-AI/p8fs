#!/usr/bin/env python3
"""Utility script to verify embedding tables and data in PostgreSQL."""

import sys

import psycopg2


def verify_database_state(connection_string: str, tenant_id: str = None):
    """Verify the state of embeddings in the database."""
    
    print("\n🔍 Verifying database state...")
    print(f"Connection: {connection_string.split('@')[1] if '@' in connection_string else connection_string}")
    if tenant_id:
        print(f"Tenant ID: {tenant_id}")
    
    try:
        conn = psycopg2.connect(connection_string)
        cursor = conn.cursor()
        
        # Check schemas
        print("\n📋 Database Schemas:")
        cursor.execute("""
            SELECT schema_name 
            FROM information_schema.schemata 
            WHERE schema_name NOT IN ('pg_catalog', 'information_schema')
            ORDER BY schema_name
        """)
        schemas = cursor.fetchall()
        for schema in schemas:
            print(f"  - {schema[0]}")
        
        # Check if embeddings schema exists
        if any(s[0] == 'embeddings' for s in schemas):
            print("\n✅ Embeddings schema exists")
            
            # List embedding tables
            print("\n📊 Embedding Tables:")
            cursor.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'embeddings'
                ORDER BY table_name
            """)
            tables = cursor.fetchall()
            for table in tables:
                print(f"  - embeddings.{table[0]}")
                
                # Get row count
                cursor.execute(f"SELECT COUNT(*) FROM embeddings.{table[0]}")
                count = cursor.fetchone()[0]
                print(f"    Rows: {count}")
                
                # Get table structure
                cursor.execute(f"""
                    SELECT column_name, data_type 
                    FROM information_schema.columns 
                    WHERE table_schema = 'embeddings' AND table_name = '{table[0]}'
                    ORDER BY ordinal_position
                """)
                columns = cursor.fetchall()
                print("    Columns:")
                for col, dtype in columns:
                    print(f"      - {col}: {dtype}")
        else:
            print("\n⚠️  Embeddings schema does not exist")
        
        # Check resources table
        print("\n📦 Resources Table:")
        cursor.execute("""
            SELECT COUNT(*) FROM resources
        """)
        resource_count = cursor.fetchone()[0]
        print(f"  Total resources: {resource_count}")
        
        if tenant_id:
            cursor.execute("""
                SELECT COUNT(*) FROM resources WHERE tenant_id = %s
            """, (tenant_id,))
            tenant_count = cursor.fetchone()[0]
            print(f"  Resources for tenant: {tenant_count}")
        
        # Sample resources
        print("\n📄 Sample Resources:")
        query = "SELECT id, name, resource_type FROM resources"
        params = ()
        if tenant_id:
            query += " WHERE tenant_id = %s"
            params = (tenant_id,)
        query += " LIMIT 5"
        
        cursor.execute(query, params)
        resources = cursor.fetchall()
        for rid, name, rtype in resources:
            print(f"  - {rid}: {name} ({rtype})")
        
        # Check embeddings if table exists
        if any(t[0] == 'resources_embeddings' for t in tables):
            print("\n🧮 Embeddings Status:")
            
            # Count embeddings
            query = "SELECT COUNT(*) FROM embeddings.resources_embeddings"
            params = ()
            if tenant_id:
                query += " WHERE tenant_id = %s"
                params = (tenant_id,)
            
            cursor.execute(query, params)
            embedding_count = cursor.fetchone()[0]
            print(f"  Total embeddings: {embedding_count}")
            
            # Count by field
            query = """
                SELECT field_name, COUNT(*) as count 
                FROM embeddings.resources_embeddings
            """
            if tenant_id:
                query += " WHERE tenant_id = %s"
            query += " GROUP BY field_name"
            
            cursor.execute(query, params)
            field_counts = cursor.fetchall()
            if field_counts:
                print("  By field:")
                for field, count in field_counts:
                    print(f"    - {field}: {count}")
            
            # Check vector dimensions
            query = """
                SELECT DISTINCT vector_dimension 
                FROM embeddings.resources_embeddings
            """
            if tenant_id:
                query += " WHERE tenant_id = %s"
            
            cursor.execute(query, params)
            dimensions = cursor.fetchall()
            if dimensions:
                print(f"  Vector dimensions: {[d[0] for d in dimensions]}")
            
            # Sample embeddings
            query = """
                SELECT entity_id, field_name, embedding_provider, 
                       vector_dimension, created_at
                FROM embeddings.resources_embeddings
            """
            if tenant_id:
                query += " WHERE tenant_id = %s"
            query += " LIMIT 3"
            
            cursor.execute(query, params)
            samples = cursor.fetchall()
            if samples:
                print("\n  Sample embeddings:")
                for entity_id, field, provider, dim, created in samples:
                    print(f"    - Entity: {entity_id}")
                    print(f"      Field: {field}, Provider: {provider}")
                    print(f"      Dimensions: {dim}, Created: {created}")
        
        print("\n✅ Database verification complete")
        
    except psycopg2.Error as e:
        print(f"\n❌ Database error: {e}")
        return False
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return False
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()
    
    return True


def check_pgvector_extension(connection_string: str):
    """Check if pgvector extension is installed."""
    print("\n🔧 Checking pgvector extension...")
    
    try:
        conn = psycopg2.connect(connection_string)
        cursor = conn.cursor()
        
        # Check if extension exists
        cursor.execute("""
            SELECT * FROM pg_extension WHERE extname = 'vector'
        """)
        result = cursor.fetchone()
        
        if result:
            print("✅ pgvector extension is installed")
        else:
            print("⚠️  pgvector extension is NOT installed")
            print("   Run: CREATE EXTENSION vector;")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Error checking pgvector: {e}")


if __name__ == "__main__":
    # Default connection string for tests (using p8fs docker-compose)
    conn_str = "postgresql://postgres:postgres@localhost:5438/app"
    tenant_id = None
    
    if len(sys.argv) > 1:
        conn_str = sys.argv[1]
    if len(sys.argv) > 2:
        tenant_id = sys.argv[2]
    
    print("=" * 60)
    print("P8FS Embedding Database Verification")
    print("=" * 60)
    
    # Check pgvector first
    check_pgvector_extension(conn_str)
    
    # Verify database state
    verify_database_state(conn_str, tenant_id)
    
    print("\n" + "=" * 60)