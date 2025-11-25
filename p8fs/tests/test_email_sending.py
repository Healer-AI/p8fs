"""Test email sending with proper subject line.

This test verifies that the dreaming worker sends emails with the correct subject:
"Your Daily Moments" (not "EEPIS Moments: <moment name>")
"""

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from p8fs.models.p8 import Moment
from p8fs.workers.dreaming import DreamingWorker


async def test_email_subject():
    """Test that email is sent with correct subject line."""

    # Create sample moments
    moments = [
        Moment(
            id=uuid4(),
            tenant_id="tenant-test",
            name="Morning Planning Session",
            content="Reviewed project goals and aligned on priorities for the week ahead.",
            summary="Weekly planning and goal alignment session",
            moment_type="planning",
            emotion_tags=["focused", "optimistic"],
            topic_tags=["work", "planning", "goals"],
            resource_timestamp=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc)
        ),
        Moment(
            id=uuid4(),
            tenant_id="tenant-test",
            name="Team Standup Discussion",
            content="Discussed blockers and upcoming deliverables with the engineering team.",
            summary="Daily standup with team alignment",
            moment_type="meeting",
            emotion_tags=["collaborative", "productive"],
            topic_tags=["work", "team", "engineering"],
            resource_timestamp=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc)
        ),
        Moment(
            id=uuid4(),
            tenant_id="tenant-test",
            name="Questions about Setting Up Life Goals",
            content="Explored personal goal-setting frameworks and reflection practices.",
            summary="Personal development and goal-setting exploration",
            moment_type="reflection",
            emotion_tags=["reflective", "curious"],
            topic_tags=["personal-development", "goals", "planning"],
            resource_timestamp=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc)
        )
    ]

    # Initialize worker
    worker = DreamingWorker()

    # Test email sending
    recipient_email = "amartey@gmail.com"

    print(f"\n{'=' * 80}")
    print("Testing Email Subject Line")
    print(f"{'=' * 80}\n")
    print(f"Sending {len(moments)} moments to {recipient_email}")
    print(f"Expected subject: 'Your Daily Moments'")
    print(f"NOT: 'EEPIS Moments: Questions about Setting Up Life Goals'\n")

    # This will use the _send_moments_email method which has the FIXED subject
    email_sent = await worker._send_moments_email(
        moments=moments,
        recipient_email=recipient_email,
        tenant_id="tenant-test"
    )

    if email_sent:
        print("✅ Email sent successfully!")
        print("\nPlease check your inbox and verify:")
        print("  1. Subject line is: 'Your Daily Moments'")
        print("  2. Email contains all 3 moments")
        print("  3. No spurious subject like 'EEPIS Moments: <moment name>'")
    else:
        print("❌ Email sending failed")
        print("\nCheck:")
        print("  1. P8FS_EMAIL_ENABLED=true")
        print("  2. P8FS_EMAIL_PASSWORD is set")
        print("  3. Email credentials are correct")

    print(f"\n{'=' * 80}\n")

    # Clean up
    await worker.cleanup()


if __name__ == "__main__":
    asyncio.run(test_email_subject())
