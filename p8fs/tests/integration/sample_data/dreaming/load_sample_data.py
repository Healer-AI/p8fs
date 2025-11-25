"""Load sample data for dreaming integration tests."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from p8fs_cluster.config.settings import config
from p8fs_cluster.logging import get_logger
from p8fs.providers import get_provider
from p8fs.repository.TenantRepository import TenantRepository
from p8fs.models.p8 import Resources, Session

logger = get_logger(__name__)

# Sample data directory
SAMPLE_DATA_DIR = Path(__file__).parent


class SampleDataLoader:
    """Loader for sample dreaming test data."""

    def __init__(self, tenant_id: str = "tenant-test"):
        """Initialize loader."""
        self.tenant_id = tenant_id
        self.provider = get_provider()
        self.repo = TenantRepository(self.provider, tenant_id=tenant_id)

    def load_resource_from_file(
        self,
        file_path: Path,
        category: str,
        resource_type: str,
        timestamp: datetime
    ) -> str:
        """
        Load a single resource from markdown file.

        Args:
            file_path: Path to markdown file
            category: Resource category
            resource_type: Type (voice_memo, document, technical)
            timestamp: Resource timestamp

        Returns:
            Resource ID
        """
        with open(file_path, 'r') as f:
            content = f.read()

        # Extract title from first line (assumes # Title format)
        lines = content.split('\n')
        title = lines[0].strip('#').strip() if lines else file_path.stem

        # Create resource
        resource = Resources(
            id=str(uuid4()),
            tenant_id=self.tenant_id,
            name=title,
            category=category,
            content=content,
            summary=f"{resource_type} - {title}",
            uri=f"file://{file_path.name}",
            resource_timestamp=timestamp,
            metadata={
                "source": "sample_data",
                "file_name": file_path.name,
                "resource_type": resource_type
            },
            resource_type=resource_type,
            related_entities=[]  # Will be populated by entity extraction
        )

        # Save to database
        saved = self.repo.create(resource)
        logger.info(f"Loaded resource: {resource.name} ({resource.id})")

        return resource.id

    def load_voice_memos(self) -> list[str]:
        """Load all voice memo transcripts."""
        voice_memo_dir = SAMPLE_DATA_DIR / "resources" / "voice_memos"

        # Define timestamps (spread over 5 days)
        base_date = datetime(2025, 1, 5, 8, 30, 0, tzinfo=timezone.utc)

        files = [
            ("morning_planning_2025_01_05.md", base_date),
            ("team_standup_2025_01_06.md", base_date + timedelta(days=1, hours=5, minutes=30)),
            ("client_call_acme_2025_01_07.md", base_date + timedelta(days=2, hours=1, minutes=30)),
            ("reflection_evening_2025_01_08.md", base_date + timedelta(days=3, hours=10)),
        ]

        resource_ids = []
        for filename, timestamp in files:
            file_path = voice_memo_dir / filename
            if file_path.exists():
                resource_id = self.load_resource_from_file(
                    file_path,
                    category="voice_memo",
                    resource_type="transcript",
                    timestamp=timestamp
                )
                resource_ids.append(resource_id)
            else:
                logger.warning(f"File not found: {file_path}")

        logger.info(f"Loaded {len(resource_ids)} voice memos")
        return resource_ids

    def load_documents(self) -> list[str]:
        """Load all document files."""
        doc_dir = SAMPLE_DATA_DIR / "resources" / "documents"

        # Documents have earlier timestamps (project started before voice memos)
        base_date = datetime(2025, 1, 3, 10, 0, 0, tzinfo=timezone.utc)

        files = [
            ("project_alpha_spec.md", base_date),
            ("acme_contract_2025.md", base_date + timedelta(days=1)),
        ]

        resource_ids = []
        for filename, timestamp in files:
            file_path = doc_dir / filename
            if file_path.exists():
                resource_id = self.load_resource_from_file(
                    file_path,
                    category="document",
                    resource_type="specification",
                    timestamp=timestamp
                )
                resource_ids.append(resource_id)
            else:
                logger.warning(f"File not found: {file_path}")

        logger.info(f"Loaded {len(resource_ids)} documents")
        return resource_ids

    def load_technical_docs(self) -> list[str]:
        """Load technical documentation."""
        tech_dir = SAMPLE_DATA_DIR / "resources" / "technical"

        base_date = datetime(2025, 1, 6, 14, 0, 0, tzinfo=timezone.utc)

        files = [
            ("architecture_overview.md", base_date),
        ]

        resource_ids = []
        for filename, timestamp in files:
            file_path = tech_dir / filename
            if file_path.exists():
                resource_id = self.load_resource_from_file(
                    file_path,
                    category="technical",
                    resource_type="architecture_doc",
                    timestamp=timestamp
                )
                resource_ids.append(resource_id)
            else:
                logger.warning(f"File not found: {file_path}")

        logger.info(f"Loaded {len(resource_ids)} technical docs")
        return resource_ids

    def load_sessions(self) -> list[str]:
        """Load chat sessions."""
        session_dir = SAMPLE_DATA_DIR / "sessions"

        session_file = session_dir / "chat_project_alpha_discussion.json"

        if not session_file.exists():
            logger.warning(f"Session file not found: {session_file}")
            return []

        with open(session_file, 'r') as f:
            session_data = json.load(f)

        # Create session
        session = Session(
            id=session_data.get("session_id", str(uuid4())),
            tenant_id=self.tenant_id,
            name="Project Alpha Discussion",
            query=session_data["messages"][0]["content"],
            metadata={
                "messages": session_data["messages"],
                "source": "sample_data"
            },
            session_type="chat",
            created_at=datetime.fromisoformat(session_data["created_at"].replace('Z', '+00:00'))
        )

        # Save session
        saved = self.repo.create(session)
        logger.info(f"Loaded session: {session.name} ({session.id})")

        return [session.id]

    def load_all(self) -> dict:
        """
        Load all sample data.

        Returns:
            Dictionary with counts of loaded resources
        """
        logger.info(f"Loading sample data for tenant: {self.tenant_id}")

        voice_memo_ids = self.load_voice_memos()
        document_ids = self.load_documents()
        technical_ids = self.load_technical_docs()
        session_ids = self.load_sessions()

        summary = {
            "voice_memos": len(voice_memo_ids),
            "documents": len(document_ids),
            "technical_docs": len(technical_ids),
            "sessions": len(session_ids),
            "total_resources": len(voice_memo_ids) + len(document_ids) + len(technical_ids),
            "resource_ids": {
                "voice_memos": voice_memo_ids,
                "documents": document_ids,
                "technical": technical_ids
            },
            "session_ids": session_ids
        }

        logger.info("Sample data loading complete:")
        logger.info(f"  Voice memos: {summary['voice_memos']}")
        logger.info(f"  Documents: {summary['documents']}")
        logger.info(f"  Technical docs: {summary['technical_docs']}")
        logger.info(f"  Sessions: {summary['sessions']}")
        logger.info(f"  Total resources: {summary['total_resources']}")

        return summary


def main():
    """Load sample data as standalone script."""
    import asyncio

    async def load():
        loader = SampleDataLoader(tenant_id="tenant-test")
        summary = loader.load_all()
        return summary

    summary = asyncio.run(load())
    print(f"\nLoaded {summary['total_resources']} resources and {summary['sessions']} sessions")


if __name__ == "__main__":
    main()
