#!/usr/bin/env python3
"""
Seed test data for REM testing

Creates comprehensive test data across multiple tenants:
- Resources (documents, transcripts, notes)
- Moments (with temporal boundaries)
- Entities (people, projects, organizations)
- Graph relationships

Usage:
    python scripts/rem/seed_test_data.py --provider postgresql
    python scripts/rem/seed_test_data.py --provider tidb --tenants 5
"""

import asyncio
import argparse
from datetime import datetime, timedelta
from typing import Optional
import uuid

from p8fs.providers import get_provider
from p8fs.repository.TenantRepository import TenantRepository
from p8fs.models.p8 import Moment
from p8fs.models.engram.models import Person, Speaker
from p8fs_cluster.logging import get_logger
from p8fs_cluster.config.settings import config

logger = get_logger(__name__)


# Sample data templates
DEVELOPERS = [
    {"name": "Alice Chen", "role": "Tech Lead"},
    {"name": "Bob Martinez", "role": "Backend Engineer"},
    {"name": "Carol Kim", "role": "Frontend Engineer"},
    {"name": "Dave Patel", "role": "DevOps Engineer"},
]

PRODUCT_MANAGERS = [
    {"name": "Emily Santos", "role": "Product Manager"},
    {"name": "Frank Wilson", "role": "Engineering Manager"},
    {"name": "Grace Lee", "role": "Design Lead"},
]

RESEARCHERS = [
    {"name": "Dr. James Smith", "role": "Research Advisor"},
    {"name": "Jane Doe", "role": "PhD Candidate"},
    {"name": "Tom Anderson", "role": "Postdoc"},
]

# Organization hierarchy for TRAVERSE testing
ORG_HIERARCHY = [
    {
        "name": "Sarah Chen",
        "role": "CEO",
        "category": "person",
        "content": "Sarah Chen is the CEO of the company, responsible for overall strategy and direction.",
        "graph_paths": []
    },
    {
        "name": "Michael Torres",
        "role": "VP Engineering",
        "category": "person",
        "content": "Michael Torres is the VP of Engineering, leading the engineering organization.",
        "graph_paths": [
            {
                "dst": "Sarah Chen",
                "rel_type": "reports-to",
                "weight": 1.0,
                "properties": {"dst_entity_type": "person/executive"},
                "created_at": "2024-01-01T10:00:00Z"
            }
        ]
    },
    {
        "name": "Alice Chen",
        "role": "Tech Lead",
        "category": "person",
        "content": "Alice Chen is a Tech Lead in the engineering organization.",
        "graph_paths": [
            {
                "dst": "Michael Torres",
                "rel_type": "reports-to",
                "weight": 1.0,
                "properties": {"dst_entity_type": "person/manager"},
                "created_at": "2024-02-01T10:00:00Z"
            },
            {
                "dst": "Bob Martinez",
                "rel_type": "manages",
                "weight": 0.9,
                "properties": {"dst_entity_type": "person/engineer"},
                "created_at": "2024-02-15T10:00:00Z"
            },
            {
                "dst": "Carol Kim",
                "rel_type": "manages",
                "weight": 0.9,
                "properties": {"dst_entity_type": "person/engineer"},
                "created_at": "2024-02-20T10:00:00Z"
            }
        ]
    },
    {
        "name": "Bob Martinez",
        "role": "Backend Engineer",
        "category": "person",
        "content": "Bob Martinez is a Backend Engineer focusing on API development and database optimization.",
        "graph_paths": [
            {
                "dst": "Alice Chen",
                "rel_type": "reports-to",
                "weight": 1.0,
                "properties": {"dst_entity_type": "person/lead"},
                "created_at": "2024-02-15T10:00:00Z"
            },
            {
                "dst": "api-redesign",
                "rel_type": "works-on",
                "weight": 0.95,
                "properties": {"dst_entity_type": "project/engineering"},
                "created_at": "2024-03-01T10:00:00Z"
            }
        ]
    },
    {
        "name": "Carol Kim",
        "role": "Frontend Engineer",
        "category": "person",
        "content": "Carol Kim is a Frontend Engineer specializing in React and user interface development.",
        "graph_paths": [
            {
                "dst": "Alice Chen",
                "rel_type": "reports-to",
                "weight": 1.0,
                "properties": {"dst_entity_type": "person/lead"},
                "created_at": "2024-02-20T10:00:00Z"
            },
            {
                "dst": "mobile-app-launch",
                "rel_type": "works-on",
                "weight": 0.9,
                "properties": {"dst_entity_type": "project/product"},
                "created_at": "2024-03-05T10:00:00Z"
            }
        ]
    },
    {
        "name": "Dave Patel",
        "role": "DevOps Engineer",
        "category": "person",
        "content": "Dave Patel is a DevOps Engineer managing infrastructure and CI/CD pipelines.",
        "graph_paths": [
            {
                "dst": "Michael Torres",
                "rel_type": "reports-to",
                "weight": 1.0,
                "properties": {"dst_entity_type": "person/manager"},
                "created_at": "2024-02-10T10:00:00Z"
            },
            {
                "dst": "ci-cd-pipeline",
                "rel_type": "owns",
                "weight": 1.0,
                "properties": {"dst_entity_type": "project/infrastructure"},
                "created_at": "2024-03-10T10:00:00Z"
            }
        ]
    }
]

PROJECTS_DEV = [
    "api-redesign",
    "database-migration",
    "auth-system",
    "microservices-platform",
    "ci-cd-pipeline",
]

PROJECTS_PM = [
    "mobile-app-launch",
    "feature-parity",
    "user-onboarding",
    "analytics-dashboard",
]

PROJECTS_RESEARCH = [
    "neural-networks-study",
    "climate-modeling",
    "data-analysis-pipeline",
]

TECHNICAL_DOCS = [
    {
        "name": "API Redesign Specification",
        "category": "technical_spec",
        "content": """# API Redesign Specification

## Overview
Complete redesign of REST API to support microservices architecture.

## Goals
- Improve scalability
- Reduce latency
- Support versioning
- Enable backward compatibility

## Architecture
Moving from monolithic API to distributed services:
- User Service
- Authentication Service
- Data Service
- Notification Service

## Timeline
Q1 2024 - Design phase
Q2 2024 - Implementation
Q3 2024 - Testing and rollout

## Team
Tech Lead: Alice Chen
Backend: Bob Martinez
DevOps: Dave Patel""",
        "entities": ["api-redesign", "alice-chen", "bob-martinez", "dave-patel"],
    },
    {
        "name": "Database Migration Guide",
        "category": "documentation",
        "content": """# Database Migration Guide

## Objective
Migrate from PostgreSQL to TiDB for improved scalability.

## Migration Strategy
1. Dual-write phase (2 weeks)
2. Validation phase (1 week)
3. Read migration (2 weeks)
4. Cleanup phase (1 week)

## Data Model Changes
- Add tenant_id to all tables
- Convert JSONB to native JSON
- Update vector indices

## Rollback Plan
Maintain PostgreSQL as backup for 30 days post-migration.

## Owners
Database: Bob Martinez
Infrastructure: Dave Patel""",
        "entities": ["database-migration", "bob-martinez", "dave-patel"],
    },
    {
        "name": "Authentication System Design",
        "category": "technical_spec",
        "content": """# Authentication System Design

## Current State
Basic username/password authentication with session cookies.

## Proposed Changes
- OAuth 2.1 device flow
- Mobile keypair generation
- JWT token issuance
- Refresh token rotation

## Security Considerations
- End-to-end encryption
- Client-held keys
- Multi-factor authentication support
- Biometric authentication (mobile)

## Implementation Phases
Phase 1: Device flow (4 weeks)
Phase 2: Mobile keypair (3 weeks)
Phase 3: Token management (2 weeks)
Phase 4: Migration (2 weeks)

## Team
Lead: Alice Chen
Backend: Bob Martinez
Mobile: Carol Kim""",
        "entities": ["auth-system", "alice-chen", "bob-martinez", "carol-kim"],
    },
]

MEETING_TRANSCRIPTS = [
    {
        "name": "Daily Standup - Jan 15",
        "category": "meeting",
        "content": """Daily Standup Transcript
Date: January 15, 2024
Time: 9:00 AM
Attendees: Alice, Bob, Dave

Alice: Good morning team. Let's do quick updates. Bob, you start.

Bob: Working on the database migration scripts. Completed the dual-write implementation yesterday. Testing phase starts today. Blocked on getting access to the TiDB staging cluster.

Alice: I can help with that. Dave, can you grant Bob access this morning?

Dave: Yep, will do right after standup.

Bob: Thanks. Should be able to complete testing by end of week.

Alice: Great. Dave, your update?

Dave: Finished the CI/CD pipeline for the new microservices. All services now have automated deployments. Next up is monitoring and alerting setup.

Alice: Excellent progress. I'm working on the API redesign spec. Should have the draft ready for review by Wednesday.

Bob: Looking forward to reviewing it.

Alice: Any blockers?

Dave: Nope, all good.

Bob: Just the TiDB access.

Alice: Alright, let's sync again tomorrow. Have a productive day everyone!""",
        "entities": ["alice-chen", "bob-martinez", "dave-patel", "database-migration", "ci-cd-pipeline", "api-redesign"],
    }
]


async def create_file_with_chunks(
    repository: TenantRepository,
    tenant_id: str,
    filename: str,
    content: str,
    mime_type: str = "text/plain",
    chunk_size: int = 500,
    timestamp: Optional[datetime] = None,
) -> tuple[dict, list[dict]]:
    """Create a file entry with associated resource chunks"""
    from p8fs.models.p8 import Files, Resources

    file_id = str(uuid.uuid4())
    upload_time = timestamp or datetime.utcnow()

    # Create file entry
    file_data = {
        "id": file_id,
        "tenant_id": tenant_id,
        "uri": f"s3://bucket/{tenant_id}/{filename}",
        "file_size": len(content),
        "mime_type": mime_type,
        "content_hash": str(hash(content)),
        "upload_timestamp": upload_time,
        "metadata": {
            "filename": filename,
            "source": "seed_script"
        },
    }

    file_obj = Files(**file_data)
    file_repo = TenantRepository(Files, tenant_id, provider_name=repository.provider_name)
    await file_repo.put(file_obj)
    logger.info(f"Created file: {filename} ({file_id}) for tenant {tenant_id}")

    # Create resource chunks
    chunks = []
    chunk_texts = [content[i:i+chunk_size] for i in range(0, len(content), chunk_size)]

    for ordinal, chunk_text in enumerate(chunk_texts):
        chunk_data = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "name": f"{filename} - Chunk {ordinal + 1}",
            "content": chunk_text,
            "category": "document_chunk",
            "ordinal": ordinal,
            "uri": file_data["uri"],
            "resource_timestamp": upload_time,
            "metadata": {
                "file_id": file_id,
                "source_file": filename,
                "chunk_index": ordinal,
                "total_chunks": len(chunk_texts),
            },
        }

        resource = Resources(**chunk_data)
        await repository.put(resource)
        chunks.append(chunk_data)

    logger.info(f"Created {len(chunks)} chunks for file {filename}")
    return file_data, chunks


async def create_resource(
    repository: TenantRepository,
    tenant_id: str,
    name: str,
    content: str,
    category: str,
    entities: list[str],
    timestamp: Optional[datetime] = None,
) -> dict:
    """Create a resource with metadata"""
    from p8fs.models.p8 import Resources

    resource_data = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "name": name,
        "content": content,
        "category": category,
        "graph_paths": [
            {
                "dst": entity,
                "rel": "mentions",
                "entity_type": "project" if "-" in entity else "person"
            }
            for entity in entities
        ],
        "resource_timestamp": timestamp or datetime.utcnow(),
        "metadata": {},
    }

    resource = Resources(**resource_data)
    success = await repository.put(resource)
    logger.info(f"Created resource: {name} for tenant {tenant_id}")
    return resource_data


async def create_moment(
    repository: TenantRepository,
    tenant_id: str,
    name: str,
    content: str,
    summary: str,
    moment_type: str,
    persons: list[dict],
    speakers: list[dict],
    emotions: list[str],
    topics: list[str],
    start_time: datetime,
    end_time: datetime,
) -> dict:
    """Create a moment with all metadata"""
    moment_data = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "name": name,
        "content": content,
        "summary": summary,
        "present_persons": [Person(**p).model_dump() for p in persons],
        "speakers": [Speaker(**s).model_dump() for s in speakers],
        "location": "Office",
        "moment_type": moment_type,
        "emotion_tags": emotions,
        "topic_tags": topics,
        "resource_timestamp": start_time,
        "resource_ends_timestamp": end_time,
        "metadata": {},
    }

    moment = Moment(**moment_data)
    success = await repository.put(moment)
    logger.info(f"Created moment: {name} for tenant {tenant_id}")
    return moment_data


async def seed_developer_tenant(repository: TenantRepository, tenant_id: str, base_date: datetime):
    """Seed data for software developer scenario"""
    logger.info(f"Seeding developer tenant: {tenant_id}")

    # Create technical documentation as files with chunks
    for i, doc in enumerate(TECHNICAL_DOCS):
        timestamp = base_date - timedelta(days=14 - i * 2)
        # Create file with chunks
        filename = f"{doc['name'].replace(' ', '_').lower()}.md"
        await create_file_with_chunks(
            repository,
            tenant_id,
            filename,
            doc["content"],
            mime_type="text/markdown",
            chunk_size=400,
            timestamp=timestamp,
        )

    # Create meeting moments
    for i in range(5):
        day_offset = i * 2
        start_time = base_date - timedelta(days=14 - day_offset, hours=9)
        end_time = start_time + timedelta(minutes=15)

        await create_moment(
            repository,
            tenant_id,
            f"Daily Standup - Day {i+1}",
            MEETING_TRANSCRIPTS[0]["content"],
            "Team sync on current sprint progress",
            "meeting",
            [{"name": p["name"], "role": p["role"]} for p in DEVELOPERS[:3]],
            [{"name": DEVELOPERS[0]["name"], "speaking_time": 180}],
            ["focused", "collaborative"],
            ["sprint-planning", "blockers", "updates"],
            start_time,
            end_time,
        )

    # Create coding session moments
    for i in range(8):
        day_offset = i
        start_time = base_date - timedelta(days=14 - day_offset, hours=14)
        end_time = start_time + timedelta(hours=2)

        await create_moment(
            repository,
            tenant_id,
            f"Coding Session - {PROJECTS_DEV[i % len(PROJECTS_DEV)]}",
            f"Deep work session on {PROJECTS_DEV[i % len(PROJECTS_DEV)]}. Implemented core features and wrote unit tests.",
            f"Productive coding session",
            "coding",
            [{"name": DEVELOPERS[i % len(DEVELOPERS)]["name"]}],
            [],
            ["focused", "productive"],
            ["development", PROJECTS_DEV[i % len(PROJECTS_DEV)]],
            start_time,
            end_time,
        )


async def seed_product_manager_tenant(repository: TenantRepository, tenant_id: str, base_date: datetime):
    """Seed data for product manager scenario"""
    logger.info(f"Seeding product manager tenant: {tenant_id}")

    # Create PRDs
    for i, project in enumerate(PROJECTS_PM):
        timestamp = base_date - timedelta(days=20 - i * 3)
        content = f"""# Product Requirements: {project}

## Vision
Drive user engagement through {project}.

## Success Metrics
- User activation rate: +25%
- Retention: +15%
- NPS: 50+

## Key Features
1. Feature Alpha
2. Feature Beta
3. Feature Gamma

## Timeline
Q1 2024

## Stakeholders
Product: Emily Santos
Engineering: Frank Wilson
Design: Grace Lee"""

        await create_resource(
            repository,
            tenant_id,
            f"{project.title()} PRD",
            content,
            "product_spec",
            [project] + [p["name"].lower().replace(" ", "-") for p in PRODUCT_MANAGERS],
            timestamp,
        )

    # Create stakeholder meetings
    for i in range(6):
        start_time = base_date - timedelta(days=20 - i * 3, hours=14)
        end_time = start_time + timedelta(hours=1)

        await create_moment(
            repository,
            tenant_id,
            f"Stakeholder Meeting - Week {i+1}",
            "Discussed roadmap priorities and resource allocation for upcoming quarter.",
            "Strategic planning session with leadership team",
            "meeting",
            [{"name": p["name"], "role": p["role"]} for p in PRODUCT_MANAGERS],
            [
                {"name": PRODUCT_MANAGERS[0]["name"], "speaking_time": 900},
                {"name": PRODUCT_MANAGERS[1]["name"], "speaking_time": 600},
            ],
            ["strategic", "collaborative"],
            ["roadmap", "priorities", "planning"],
            start_time,
            end_time,
        )


async def seed_researcher_tenant(repository: TenantRepository, tenant_id: str, base_date: datetime):
    """Seed data for academic researcher scenario"""
    logger.info(f"Seeding researcher tenant: {tenant_id}")

    # Create research notes
    for i, project in enumerate(PROJECTS_RESEARCH):
        timestamp = base_date - timedelta(days=25 - i * 4)
        content = f"""# Research Notes: {project}

## Hypothesis
Testing neural network architectures for {project}.

## Methodology
1. Literature review
2. Experiment design
3. Data collection
4. Analysis

## Preliminary Results
Initial experiments show promising results. Further validation needed.

## Next Steps
- Refine model architecture
- Expand dataset
- Statistical analysis

## Team
Advisor: Dr. James Smith
PhD Student: Jane Doe
Postdoc: Tom Anderson"""

        await create_resource(
            repository,
            tenant_id,
            f"{project.title()} Research Notes",
            content,
            "research_notes",
            [project] + [p["name"].lower().replace(" ", "-").replace(".", "") for p in RESEARCHERS],
            timestamp,
        )

    # Create lab meetings
    for i in range(4):
        start_time = base_date - timedelta(days=25 - i * 6, hours=10)
        end_time = start_time + timedelta(hours=2)

        await create_moment(
            repository,
            tenant_id,
            f"Lab Meeting - Week {i+1}",
            "Presented research progress and discussed methodology refinements.",
            "Weekly research group meeting",
            "meeting",
            [{"name": p["name"], "role": p["role"]} for p in RESEARCHERS],
            [
                {"name": RESEARCHERS[1]["name"], "speaking_time": 1800},
                {"name": RESEARCHERS[0]["name"], "speaking_time": 1200},
            ],
            ["analytical", "curious"],
            ["research", "methodology", "results"],
            start_time,
            end_time,
        )


async def seed_org_hierarchy_tenant(repository: TenantRepository, tenant_id: str, base_date: datetime):
    """Seed organization hierarchy data for TRAVERSE testing"""
    logger.info(f"Seeding organization hierarchy tenant: {tenant_id}")

    from p8fs.models.p8 import Resources
    import json

    # Create person resources with proper InlineEdge graph relationships
    for i, person in enumerate(ORG_HIERARCHY):
        timestamp = base_date - timedelta(days=30 - i)

        resource_data = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "name": person["name"],
            "content": person["content"],
            "category": person["category"],
            "graph_paths": person["graph_paths"],  # InlineEdge format
            "resource_timestamp": timestamp,
            "metadata": {"role": person["role"]},
        }

        resource = Resources(**resource_data)
        success = await repository.put(resource)
        logger.info(f"Created person: {person['name']} with {len(person['graph_paths'])} edges")


async def populate_kv_mappings(repository: TenantRepository, tenant_id: str):
    """Populate KV reverse mappings for LOOKUP queries"""
    logger.info(f"Populating KV mappings for tenant {tenant_id}")

    # This would typically be done by the repository during resource creation
    # For testing, we can verify KV population separately
    pass


async def main():
    from p8fs.models.p8 import Resources

    parser = argparse.ArgumentParser(description="Seed REM test data")
    parser.add_argument(
        "--provider",
        choices=["postgresql", "tidb"],
        default="postgresql",
        help="Database provider",
    )
    parser.add_argument(
        "--tenants",
        type=int,
        default=3,
        help="Number of test tenants to create",
    )
    args = parser.parse_args()

    # Override config
    config.storage_provider = args.provider

    base_date = datetime.utcnow()

    # Create test tenants
    tenant_scenarios = [
        ("dev-tenant-001", seed_developer_tenant),
        ("pm-tenant-002", seed_product_manager_tenant),
        ("research-tenant-003", seed_researcher_tenant),
        ("org-tenant-004", seed_org_hierarchy_tenant),
    ]

    success_count = 0
    failure_count = 0

    for i in range(min(args.tenants, len(tenant_scenarios))):
        tenant_id, seed_func = tenant_scenarios[i]
        # Use Resources model for repository
        repository = TenantRepository(Resources, tenant_id, provider_name=args.provider)

        try:
            await seed_func(repository, tenant_id, base_date)
            await populate_kv_mappings(repository, tenant_id)
            logger.info(f"✓ Completed seeding for {tenant_id}")
            success_count += 1
        except Exception as e:
            logger.error(f"✗ Failed seeding {tenant_id}: {e}")
            logger.exception("Full error details:")
            failure_count += 1
            # Continue with next tenant instead of stopping

    logger.info(f"Test data seeding complete: {success_count} succeeded, {failure_count} failed")


if __name__ == "__main__":
    asyncio.run(main())
