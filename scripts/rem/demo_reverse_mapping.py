#!/usr/bin/env python3
"""
Demonstrate REM Schema-Agnostic Reverse Entity Mapping via TiKV

This shows how entity lookups work WITHOUT schema knowledge or table joins.
"""

import asyncio
from p8fs.providers import get_provider
from p8fs.models.p8 import Resources
from p8fs.repository import TenantRepository

TENANT = "test-tenant"


async def main():
    kv = get_provider().kv
    repo = TenantRepository(Resources, tenant_id=TENANT)

    print("=" * 80)
    print("REM SCHEMA-AGNOSTIC REVERSE ENTITY MAPPING")
    print("=" * 80)

    # Demonstration 1: Single entity lookup
    print("\n1. LOOKUP: 'sarah-chen' (person)")
    print("-" * 80)

    # Step 1: TiKV reverse index lookup (O(1))
    entity_key = f"{TENANT}/sarah-chen/resource"
    kv_data = await kv.get(entity_key)

    print(f"   TiKV Key: {entity_key}")
    print(f"   Entity Type: {kv_data.get('entity_type')}")
    print(f"   Resource IDs: {len(kv_data.get('entity_ids', []))}")

    # Step 2: Fetch resources (batch operation)
    entity_ids = kv_data.get('entity_ids', [])
    all_resources = await repo.select(filters={'tenant_id': TENANT}, limit=100)
    matching = [r for r in all_resources if str(r.id) in entity_ids]

    print(f"\n   Resources mentioning 'sarah-chen':")
    for r in matching:
        print(f"     • {r.name}")

    # Demonstration 2: Multi-entity query (AND operation)
    print("\n\n2. COMPLEX QUERY: 'sarah-chen' AND 'tidb'")
    print("-" * 80)

    # Get both entity sets
    sarah_data = await kv.get(f"{TENANT}/sarah-chen/resource")
    tidb_data = await kv.get(f"{TENANT}/tidb/resource")

    sarah_ids = set(sarah_data.get('entity_ids', []))
    tidb_ids = set(tidb_data.get('entity_ids', []))

    # Set intersection for AND
    both_ids = sarah_ids.intersection(tidb_ids)

    print(f"   'sarah-chen': {len(sarah_ids)} resources")
    print(f"   'tidb': {len(tidb_ids)} resources")
    print(f"   BOTH: {len(both_ids)} resources")

    matching_both = [r for r in all_resources if str(r.id) in both_ids]
    print(f"\n   Resources mentioning BOTH:")
    for r in matching_both:
        print(f"     • {r.name}")
        print(f"       Entities: {[e.get('entity_id') for e in r.related_entities]}")

    # Demonstration 3: Multi-entity query (OR operation)
    print("\n\n3. COMPLEX QUERY: 'redis' OR 'postgresql'")
    print("-" * 80)

    redis_data = await kv.get(f"{TENANT}/redis/resource")
    postgres_data = await kv.get(f"{TENANT}/postgresql/resource")

    redis_ids = set(redis_data.get('entity_ids', []) if redis_data else [])
    postgres_ids = set(postgres_data.get('entity_ids', []) if postgres_data else [])

    # Set union for OR
    either_ids = redis_ids.union(postgres_ids)

    print(f"   'redis': {len(redis_ids)} resources")
    print(f"   'postgresql': {len(postgres_ids)} resources")
    print(f"   EITHER: {len(either_ids)} resources")

    matching_either = [r for r in all_resources if str(r.id) in either_ids]
    print(f"\n   Resources mentioning redis OR postgresql:")
    for r in matching_either:
        print(f"     • {r.name}")

    # Show the key benefits
    print("\n\n" + "=" * 80)
    print("SCHEMA-AGNOSTIC BENEFITS")
    print("=" * 80)
    print("""
  ✓ No SQL JOINs required
    - Traditional: SELECT * FROM resources r
                   JOIN entities e ON r.id = e.resource_id
                   WHERE e.name = 'sarah-chen'
    - REM: Single O(1) KV lookup → array of IDs

  ✓ No schema knowledge needed
    - Don't need to know table structure
    - Don't need to know foreign key relationships
    - Works the same for resources, moments, sessions, etc.

  ✓ Reverse index automatically maintained
    - When resource is created with related_entities
    - TenantRepository._populate_kv_for_entity() creates reverse mapping
    - Entity → [resource_ids] stored in TiKV

  ✓ Complex queries via set operations
    - AND: Set intersection
    - OR: Set union
    - NOT: Set difference
    - Composable without query language

  ✓ Performance characteristics
    - Entity lookup: O(1) via TiKV
    - Resource fetch: O(n) where n = matching resources
    - No database joins: No O(n*m) complexity
""")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
