"""Example script demonstrating TiDB provider usage.

This script shows how to:
1. Override the default PostgreSQL provider
2. Connect to TiDB
3. Create tables
4. Perform semantic search
5. Execute various queries
"""

import json
from datetime import datetime
from uuid import uuid4

from p8fs.models import AbstractModel
from p8fs.providers.tidb import TiDBProvider


# Define a model for our example
class Article(AbstractModel):
    """Article model with semantic search capabilities."""
    id: str
    title: str
    content: str
    author: str
    tags: list[str] = []
    published_date: datetime = None
    
    @classmethod
    def to_sql_schema(cls):
        return {
            'table_name': 'articles',
            'key_field': 'id',
            'fields': {
                'id': {'type': str, 'is_primary_key': True},
                'title': {'type': str, 'nullable': False},
                'content': {'type': str, 'is_embedding': True},
                'author': {'type': str},
                'tags': {'type': list[str]},
                'published_date': {'type': datetime}
            },
            'embedding_fields': ['content'],
            'tenant_isolated': True,
            'embedding_providers': {'content': 'openai'}
        }


def main():
    """Demonstrate TiDB provider usage."""
    print("=== TiDB Provider Example ===\n")
    
    # 1. Create TiDB provider instance (overrides default PostgreSQL)
    print("1. Creating TiDB provider...")
    provider = TiDBProvider()
    print(f"   Provider type: {provider.get_dialect_name()}")
    print(f"   Vector type: {provider.get_vector_type()}")
    
    # 2. Connect to TiDB
    print("\n2. Connecting to TiDB...")
    connection = provider.connect_sync()
    print("   Connected successfully!")
    
    # Get version info
    cursor = connection.cursor()
    cursor.execute("SELECT VERSION() as version")
    version = cursor.fetchone()['version']
    print(f"   Database version: {version}")
    
    # 3. Create tables
    print("\n3. Creating tables...")
    
    # Main table
    create_table_sql = provider.create_table_sql(Article)
    print("   Creating main table...")
    cursor.execute(create_table_sql)
    
    # Embedding table for semantic search
    embedding_sql = provider.create_embedding_table_sql(Article)
    if embedding_sql:
        print("   Creating embedding table...")
        for statement in embedding_sql.split(';'):
            if statement.strip():
                cursor.execute(statement)
    
    connection.commit()
    print("   Tables created successfully!")
    
    # 4. Insert sample data
    print("\n4. Inserting sample articles...")
    tenant_id = "demo_tenant"
    
    articles = [
        {
            'id': str(uuid4()),
            'title': 'Introduction to TiDB',
            'content': 'TiDB is a distributed SQL database that features horizontal scalability, strong consistency, and high availability.',
            'author': 'Tech Writer',
            'tags': ['database', 'tidb', 'distributed'],
            'published_date': datetime.utcnow(),
            'tenant_id': tenant_id
        },
        {
            'id': str(uuid4()),
            'title': 'Vector Search in Modern Databases',
            'content': 'Vector search enables semantic similarity matching, powering AI applications with efficient nearest neighbor queries.',
            'author': 'AI Researcher',
            'tags': ['ai', 'vectors', 'search'],
            'published_date': datetime.utcnow(),
            'tenant_id': tenant_id
        },
        {
            'id': str(uuid4()),
            'title': 'Building Scalable Applications',
            'content': 'Learn how to build applications that can scale horizontally using distributed databases and microservices architecture.',
            'author': 'Solutions Architect',
            'tags': ['scalability', 'architecture', 'distributed'],
            'published_date': datetime.utcnow(),
            'tenant_id': tenant_id
        }
    ]
    
    for article in articles:
        sql, params = provider.upsert_sql(Article, article)
        cursor.execute(sql, params)
        print(f"   Inserted: {article['title']}")
    
    connection.commit()
    
    # 5. Demonstrate various queries
    print("\n5. Executing queries...")
    
    # Basic select
    print("\n   a) Basic SELECT query:")
    sql, params = provider.select_sql(
        Article,
        filters={'tenant_id': tenant_id},
        order_by=['-published_date'],
        limit=5
    )
    results = provider.execute(connection, sql, params)
    for result in results:
        print(f"      - {result['title']} by {result['author']}")
    
    # Filter query
    print("\n   b) Filtered query (tags contain 'distributed'):")
    sql, params = provider.select_sql(
        Article,
        filters={
            'tenant_id': tenant_id,
            'tags__contains': json.dumps('distributed')
        }
    )
    results = provider.execute(connection, sql, params)
    for result in results:
        print(f"      - {result['title']}")
    
    # 6. Semantic search (if vector functions available)
    print("\n6. Testing semantic search capabilities...")
    if provider.check_vector_functions_available(connection):
        print("   Vector functions available!")
        
        # Insert mock embeddings for demonstration
        # In real usage, these would be generated by an embedding model
        print("   Inserting mock embeddings...")
        
        for i, article in enumerate(articles):
            # Create different embedding patterns for each article
            if i == 0:  # TiDB article
                embedding = [0.8 if j % 10 == 0 else 0.2 for j in range(768)]
            elif i == 1:  # Vector search article
                embedding = [0.2 if j % 10 == 0 else 0.8 for j in range(768)]
            else:  # Scalability article
                embedding = [0.5 for j in range(768)]
            
            embedding_sql = """
                INSERT INTO embeddings.articles_embeddings 
                (entity_id, field_name, embedding_vector, tenant_id, created_at)
                VALUES (%s, %s, VEC_FROM_TEXT(%s), %s, NOW())
            """
            cursor.execute(embedding_sql, (
                article['id'],
                'content',
                json.dumps(embedding),
                tenant_id
            ))
        
        connection.commit()
        
        # Perform semantic search
        print("\n   Performing semantic search for 'database technology'...")
        # Query embedding similar to first article (TiDB)
        query_embedding = [0.7 if j % 10 == 0 else 0.3 for j in range(768)]
        
        sql, params = provider.semantic_search_sql(
            Article,
            query_embedding,
            field_name='content',
            limit=3,
            tenant_id=tenant_id
        )
        
        results = provider.execute(connection, sql, params)
        print("   Search results (ordered by relevance):")
        for i, result in enumerate(results, 1):
            print(f"      {i}. {result['title']} (distance: {result.get('distance', 'N/A'):.4f})")
    else:
        print("   Vector functions not available in this TiDB instance")
    
    # 7. TiDB-specific features
    print("\n7. TiDB-specific features:")
    
    # Table statistics
    print("   a) Analyzing table for query optimization:")
    optimize_sql = provider.optimize_table_sql('articles')
    cursor.execute(optimize_sql)
    print(f"      Executed: {optimize_sql}")
    
    # TiFlash replica (for analytics)
    print("\n   b) TiFlash replica SQL (for OLAP queries):")
    tiflash_sql = provider.get_tiflash_replica_sql('articles', replicas=1)
    print(f"      {tiflash_sql}")
    
    # Placement rules
    print("\n   c) Placement rule SQL (for geo-distribution):")
    placement_sql = provider.get_placement_rule_sql('articles', region='us-east', replicas=3)
    print(f"      {placement_sql[:100]}...")  # Truncated for display
    
    # 8. Clean up
    print("\n8. Cleaning up...")
    cursor.execute("DROP TABLE IF EXISTS articles")
    cursor.execute("DROP TABLE IF EXISTS embeddings.articles_embeddings")
    connection.commit()
    
    cursor.close()
    connection.close()
    print("   Done!")
    
    print("\n=== Example completed successfully! ===")


if __name__ == "__main__":
    main()