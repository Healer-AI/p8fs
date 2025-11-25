"""
Test data factories for creating model instances with sensible defaults.

Provides builder pattern for creating test data without boilerplate.
"""

from datetime import datetime, timezone
from uuid import uuid4
from typing import Any

from p8fs.models.p8 import Resources, Session


class ResourceFactory:
    """Factory for creating Resources test instances."""

    @staticmethod
    def create(
        tenant_id: str,
        name: str | None = None,
        category: str = "document",
        content: str | None = None,
        **kwargs
    ) -> Resources:
        """
        Create a Resource with sensible defaults.

        Args:
            tenant_id: Tenant ID for multi-tenancy
            name: Resource name (auto-generated if not provided)
            category: Resource category (default: "document")
            content: Resource content (auto-generated if not provided)
            **kwargs: Additional fields to override

        Returns:
            Resources instance ready to save

        Example:
            resource = ResourceFactory.create(
                tenant_id="test-tenant",
                name="Project Spec",
                category="technical"
            )
        """
        if name is None:
            name = f"Test Resource {uuid4().hex[:8]}"

        if content is None:
            content = f"Sample content for {name}"

        defaults = {
            'id': str(uuid4()),
            'tenant_id': tenant_id,
            'name': name,
            'category': category,
            'content': content,
        }

        # Merge with any additional kwargs
        defaults.update(kwargs)

        return Resources(**defaults)

    @staticmethod
    def create_batch(
        tenant_id: str,
        count: int = 3,
        **kwargs
    ) -> list[Resources]:
        """
        Create multiple Resources with varied content.

        Args:
            tenant_id: Tenant ID
            count: Number of resources to create
            **kwargs: Common fields for all resources

        Returns:
            List of Resources instances
        """
        categories = ['document', 'voice_memo', 'technical', 'note']
        resources = []

        for i in range(count):
            resource = ResourceFactory.create(
                tenant_id=tenant_id,
                name=f"Test Resource {i+1}",
                category=categories[i % len(categories)],
                content=f"Sample content for test resource number {i+1}",
                **kwargs
            )
            resources.append(resource)

        return resources


class SessionFactory:
    """Factory for creating Session test instances."""

    @staticmethod
    def create(
        tenant_id: str,
        name: str | None = None,
        query: str | None = None,
        **kwargs
    ) -> Session:
        """
        Create a Session with sensible defaults.

        Args:
            tenant_id: Tenant ID
            name: Session name (auto-generated if not provided)
            query: Session query (auto-generated if not provided)
            **kwargs: Additional fields to override

        Returns:
            Session instance ready to save
        """
        if name is None:
            name = f"Test Session {uuid4().hex[:8]}"

        if query is None:
            query = f"Test query for {name}"

        defaults = {
            'id': str(uuid4()),
            'tenant_id': tenant_id,
            'name': name,
            'query': query,
        }

        defaults.update(kwargs)

        return Session(**defaults)

    @staticmethod
    def create_batch(
        tenant_id: str,
        count: int = 2,
        **kwargs
    ) -> list[Session]:
        """Create multiple Sessions."""
        return [
            SessionFactory.create(
                tenant_id=tenant_id,
                name=f"Test Session {i+1}",
                query=f"Test query {i+1}",
                **kwargs
            )
            for i in range(count)
        ]
