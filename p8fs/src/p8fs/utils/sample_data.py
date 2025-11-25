"""Sample data generation for new tenant onboarding.

This module provides functions to generate sample moments, sessions, and related
data for new tenants to provide a better first-time experience.
"""

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

# Unsplash image URLs for sample moments
# Using Unsplash Source API for random high-quality images
SAMPLE_IMAGES = {
    "device_setup": [
        "https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=800&q=80",  # Smart device
        "https://images.unsplash.com/photo-1531297484001-80022131f5a1?w=800&q=80",  # Tech setup
    ],
    "goal_setting": [
        "https://images.unsplash.com/photo-1484480974693-6ca0a78fb36b?w=800&q=80",  # Planning notebook
        "https://images.unsplash.com/photo-1506784983877-45594efa4cbe?w=800&q=80",  # Goal planning
    ],
    "reflection": [
        "https://images.unsplash.com/photo-1499750310107-5fef28a66643?w=800&q=80",  # Journaling
        "https://images.unsplash.com/photo-1455390582262-044cdead277a?w=800&q=80",  # Writing notes
    ],
    "career": [
        "https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?w=800&q=80",  # Professional growth
        "https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=800&q=80",  # Career planning
    ],
    "wellness": [
        "https://images.unsplash.com/photo-1506126613408-eca07ce68773?w=800&q=80",  # Wellness
        "https://images.unsplash.com/photo-1545205597-3d9d02c29597?w=800&q=80",  # Self-care
    ],
}


def create_sample_moments(tenant_id: str) -> list[dict[str, Any]]:
    """
    Create sample moments for a new Eepis user.

    These moments represent a realistic onboarding journey where a user:
    - Registers their Eepis device
    - Sets up life goals and priorities
    - Has conversations about their aspirations
    - Reflects on their progress
    - Plans next steps

    Each moment demonstrates:
    - Speaker tracking with emotions
    - Key emotional context
    - Representative images from Unsplash
    - Various moment types (reflection, planning, conversation)

    Args:
        tenant_id: The tenant ID to create moments for

    Returns:
        List of moment dictionaries ready for database insertion
    """
    now = datetime.now(timezone.utc)
    base_time = now - timedelta(days=3)  # Sample moments from the past 3 days

    moments = [
        {
            "id": str(uuid4()),
            "tenant_id": tenant_id,
            "name": "Registering Your Eepis Device",
            "category": "onboarding",
            "content": "First conversation with Eepis during device setup. Discussed initial preferences and how Eepis can help with daily life organization and goal tracking.",
            "summary": "Initial device setup and introduction to Eepis capabilities",
            "resource_timestamp": base_time,
            "resource_ends_timestamp": base_time + timedelta(minutes=12),
            "moment_type": "conversation",
            "speakers": [
                {
                    "text": "Welcome! I'm Eepis, your personal AI assistant. I'm here to help you organize your life and achieve your goals. What brings you here today?",
                    "speaker_identifier": "eepis",
                    "timestamp": (base_time + timedelta(minutes=1)).isoformat(),
                    "emotion": "welcoming",
                },
                {
                    "text": "Hi Eepis! I'm excited to get started. I've been feeling overwhelmed with work and personal goals lately, and I need help staying organized.",
                    "speaker_identifier": "user",
                    "timestamp": (base_time + timedelta(minutes=2)).isoformat(),
                    "emotion": "hopeful",
                },
                {
                    "text": "I understand. Many people feel that way. I can help you track your tasks, set meaningful goals, and even reflect on your progress. Would you like to start by sharing some of your current priorities?",
                    "speaker_identifier": "eepis",
                    "timestamp": (base_time + timedelta(minutes=3)).isoformat(),
                    "emotion": "supportive",
                },
                {
                    "text": "Yes, that would be great. I want to focus on my career growth, maintaining better work-life balance, and maybe learn a new skill this year.",
                    "speaker_identifier": "user",
                    "timestamp": (base_time + timedelta(minutes=4)).isoformat(),
                    "emotion": "motivated",
                },
            ],
            "key_emotions": ["hopeful", "welcoming", "motivated"],
            "images": SAMPLE_IMAGES["device_setup"][:1],
            "emotion_tags": ["welcoming", "hopeful", "motivated", "excited"],
            "topic_tags": ["onboarding", "device-setup", "introduction", "goals"],
            "present_persons": [
                {"id": "user", "name": "You"},
                {"id": "eepis", "name": "Eepis"},
            ],
            "uri": f"sample://moments/device-setup-{base_time.date()}",
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": str(uuid4()),
            "tenant_id": tenant_id,
            "name": "Setting Up Life Goals",
            "category": "planning",
            "content": "Defining personal and professional goals for the next six months. Discussed career advancement, health objectives, and learning aspirations with Eepis assistance in breaking down larger goals into actionable steps.",
            "summary": "Goal planning session covering career, health, and personal growth",
            "resource_timestamp": base_time + timedelta(days=1, hours=2),
            "resource_ends_timestamp": base_time + timedelta(days=1, hours=2, minutes=25),
            "moment_type": "planning",
            "speakers": [
                {
                    "text": "Let's start by identifying your top priorities. You mentioned career growth, work-life balance, and learning a new skill. Which feels most urgent to you right now?",
                    "speaker_identifier": "eepis",
                    "timestamp": (base_time + timedelta(days=1, hours=2, minutes=2)).isoformat(),
                    "emotion": "focused",
                },
                {
                    "text": "I think career growth is the most important. I want to move into a senior role within the next year, but I'm not sure what steps to take.",
                    "speaker_identifier": "user",
                    "timestamp": (base_time + timedelta(days=1, hours=2, minutes=3)).isoformat(),
                    "emotion": "determined",
                },
                {
                    "text": "That's a clear goal. Let's break it down. What skills or experiences do you think you need to develop to be ready for that senior role?",
                    "speaker_identifier": "eepis",
                    "timestamp": (base_time + timedelta(days=1, hours=2, minutes=5)).isoformat(),
                    "emotion": "encouraging",
                },
                {
                    "text": "I need to improve my leadership skills and get more experience with project management. Also, I should probably network more with people in those positions.",
                    "speaker_identifier": "user",
                    "timestamp": (base_time + timedelta(days=1, hours=2, minutes=7)).isoformat(),
                    "emotion": "thoughtful",
                },
                {
                    "text": "Excellent insights! I'll help you create a roadmap with milestones for leadership development, project management experience, and networking opportunities. We can track your progress together.",
                    "speaker_identifier": "eepis",
                    "timestamp": (base_time + timedelta(days=1, hours=2, minutes=10)).isoformat(),
                    "emotion": "supportive",
                },
            ],
            "key_emotions": ["determined", "thoughtful", "supportive"],
            "images": SAMPLE_IMAGES["goal_setting"],
            "emotion_tags": ["focused", "determined", "thoughtful", "encouraging"],
            "topic_tags": ["goals", "career-growth", "planning", "leadership", "skill-development"],
            "present_persons": [
                {"id": "user", "name": "You"},
                {"id": "eepis", "name": "Eepis"},
            ],
            "uri": f"sample://moments/goal-setting-{base_time.date()}",
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": str(uuid4()),
            "tenant_id": tenant_id,
            "name": "Discussing Career Aspirations",
            "category": "reflection",
            "content": "Deep conversation about long-term career vision and immediate next steps. Explored what success means personally and professionally, and identified potential obstacles to career advancement.",
            "summary": "Career reflection session exploring values, aspirations, and next steps",
            "resource_timestamp": base_time + timedelta(days=2, hours=3),
            "resource_ends_timestamp": base_time + timedelta(days=2, hours=3, minutes=18),
            "moment_type": "conversation",
            "speakers": [
                {
                    "text": "You mentioned wanting a senior role, but let's dig deeper. What does success look like to you beyond the title?",
                    "speaker_identifier": "eepis",
                    "timestamp": (base_time + timedelta(days=2, hours=3, minutes=2)).isoformat(),
                    "emotion": "curious",
                },
                {
                    "text": "That's a good question. I think it's about having more impact on the direction of projects and mentoring others. The title is just a recognition of that.",
                    "speaker_identifier": "user",
                    "timestamp": (base_time + timedelta(days=2, hours=3, minutes=4)).isoformat(),
                    "emotion": "reflective",
                },
                {
                    "text": "That's a mature perspective. Impact and mentorship are valuable goals. What's currently preventing you from taking on more of that responsibility?",
                    "speaker_identifier": "eepis",
                    "timestamp": (base_time + timedelta(days=2, hours=3, minutes=6)).isoformat(),
                    "emotion": "thoughtful",
                },
                {
                    "text": "I think it's partly confidence and partly not knowing how to position myself for those opportunities. I sometimes hold back when I should speak up.",
                    "speaker_identifier": "user",
                    "timestamp": (base_time + timedelta(days=2, hours=3, minutes=8)).isoformat(),
                    "emotion": "honest",
                },
                {
                    "text": "That's an important realization. Building confidence through small wins can help. What if we set a goal to contribute one strategic idea in your next team meeting?",
                    "speaker_identifier": "eepis",
                    "timestamp": (base_time + timedelta(days=2, hours=3, minutes=11)).isoformat(),
                    "emotion": "encouraging",
                },
            ],
            "key_emotions": ["reflective", "honest", "encouraging"],
            "images": SAMPLE_IMAGES["career"],
            "emotion_tags": ["reflective", "thoughtful", "honest", "encouraging"],
            "topic_tags": ["career", "aspirations", "leadership", "confidence", "mentorship"],
            "present_persons": [
                {"id": "user", "name": "You"},
                {"id": "eepis", "name": "Eepis"},
            ],
            "uri": f"sample://moments/career-discussion-{base_time.date()}",
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": str(uuid4()),
            "tenant_id": tenant_id,
            "name": "Reflecting on Progress",
            "category": "reflection",
            "content": "Weekly reflection on progress toward goals. Celebrated small wins including speaking up in a meeting and completing a leadership training module. Identified areas needing more attention like networking and work-life balance.",
            "summary": "Weekly reflection celebrating wins and identifying growth areas",
            "resource_timestamp": base_time + timedelta(days=5, hours=4),
            "resource_ends_timestamp": base_time + timedelta(days=5, hours=4, minutes=15),
            "moment_type": "reflection",
            "speakers": [
                {
                    "text": "How has your week been? Let's review your progress on the goals we set together.",
                    "speaker_identifier": "eepis",
                    "timestamp": (base_time + timedelta(days=5, hours=4, minutes=1)).isoformat(),
                    "emotion": "supportive",
                },
                {
                    "text": "It was good! I actually shared an idea in our team meeting like we discussed. It felt great to contribute more actively.",
                    "speaker_identifier": "user",
                    "timestamp": (base_time + timedelta(days=5, hours=4, minutes=3)).isoformat(),
                    "emotion": "proud",
                },
                {
                    "text": "That's wonderful progress! How did it feel? Did your team respond positively?",
                    "speaker_identifier": "eepis",
                    "timestamp": (base_time + timedelta(days=5, hours=4, minutes=5)).isoformat(),
                    "emotion": "encouraging",
                },
                {
                    "text": "Yes, they did! My manager even followed up to discuss it further. I also completed the first module of that leadership course.",
                    "speaker_identifier": "user",
                    "timestamp": (base_time + timedelta(days=5, hours=4, minutes=7)).isoformat(),
                    "emotion": "accomplished",
                },
                {
                    "text": "Excellent work! You're building momentum. What about the networking and work-life balance goals? How are those going?",
                    "speaker_identifier": "eepis",
                    "timestamp": (base_time + timedelta(days=5, hours=4, minutes=9)).isoformat(),
                    "emotion": "curious",
                },
                {
                    "text": "Honestly, I haven't made much progress there. I've been so focused on work that I haven't had time for networking or self-care.",
                    "speaker_identifier": "user",
                    "timestamp": (base_time + timedelta(days=5, hours=4, minutes=11)).isoformat(),
                    "emotion": "concerned",
                },
            ],
            "key_emotions": ["proud", "encouraging", "reflective"],
            "images": SAMPLE_IMAGES["reflection"][:1],
            "emotion_tags": ["proud", "encouraging", "reflective", "accomplished"],
            "topic_tags": ["reflection", "progress", "wins", "goals", "work-life-balance"],
            "present_persons": [
                {"id": "user", "name": "You"},
                {"id": "eepis", "name": "Eepis"},
            ],
            "uri": f"sample://moments/weekly-reflection-{base_time.date()}",
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": str(uuid4()),
            "tenant_id": tenant_id,
            "name": "Planning Next Steps",
            "category": "planning",
            "content": "Action planning session to address work-life balance and networking gaps. Created specific, time-bound commitments for the upcoming week including scheduling coffee chats and setting boundaries for work hours.",
            "summary": "Creating actionable plan for work-life balance and networking",
            "resource_timestamp": base_time + timedelta(days=6, hours=2),
            "resource_ends_timestamp": base_time + timedelta(days=6, hours=2, minutes=20),
            "moment_type": "planning",
            "speakers": [
                {
                    "text": "Let's tackle the areas where you're struggling. What's one small step you could take this week toward better work-life balance?",
                    "speaker_identifier": "eepis",
                    "timestamp": (base_time + timedelta(days=6, hours=2, minutes=2)).isoformat(),
                    "emotion": "solution-focused",
                },
                {
                    "text": "Maybe I could set a hard stop time for work each day? Like no emails after 7 PM?",
                    "speaker_identifier": "user",
                    "timestamp": (base_time + timedelta(days=6, hours=2, minutes=4)).isoformat(),
                    "emotion": "tentative",
                },
                {
                    "text": "That's a great boundary to set. Let's make it specific. How about we start with three days this week where you commit to that boundary?",
                    "speaker_identifier": "eepis",
                    "timestamp": (base_time + timedelta(days=6, hours=2, minutes=6)).isoformat(),
                    "emotion": "encouraging",
                },
                {
                    "text": "That feels doable. And for networking, I could reach out to two people for coffee chats this week.",
                    "speaker_identifier": "user",
                    "timestamp": (base_time + timedelta(days=6, hours=2, minutes=9)).isoformat(),
                    "emotion": "motivated",
                },
                {
                    "text": "Perfect! I'll help you track these commitments. Who are you thinking of reaching out to?",
                    "speaker_identifier": "eepis",
                    "timestamp": (base_time + timedelta(days=6, hours=2, minutes=11)).isoformat(),
                    "emotion": "supportive",
                },
                {
                    "text": "There's a senior engineer I've wanted to learn from, and someone from the product team who seems to have good work-life balance.",
                    "speaker_identifier": "user",
                    "timestamp": (base_time + timedelta(days=6, hours=2, minutes=13)).isoformat(),
                    "emotion": "thoughtful",
                },
                {
                    "text": "Excellent choices. Let's set reminders to help you follow through. You're making real progress!",
                    "speaker_identifier": "eepis",
                    "timestamp": (base_time + timedelta(days=6, hours=2, minutes=16)).isoformat(),
                    "emotion": "confident",
                },
            ],
            "key_emotions": ["motivated", "supportive", "solution-focused"],
            "images": SAMPLE_IMAGES["wellness"] + SAMPLE_IMAGES["goal_setting"][:1],
            "emotion_tags": ["motivated", "supportive", "solution-focused", "committed"],
            "topic_tags": ["planning", "work-life-balance", "networking", "boundaries", "action-steps"],
            "present_persons": [
                {"id": "user", "name": "You"},
                {"id": "eepis", "name": "Eepis"},
            ],
            "uri": f"sample://moments/action-planning-{base_time.date()}",
            "created_at": now,
            "updated_at": now,
        },
    ]

    return moments


def create_sample_sessions_for_moment(tenant_id: str, moment_id: str, moment_name: str) -> list[dict[str, Any]]:
    """
    Create sample chat sessions linked to a specific moment.

    Args:
        tenant_id: The tenant ID
        moment_id: The moment ID to link sessions to
        moment_name: The moment name for context

    Returns:
        List of session dictionaries ready for database insertion
    """
    now = datetime.now(timezone.utc)

    sessions = [
        {
            "id": str(uuid4()),
            "tenant_id": tenant_id,
            "moment_id": moment_id,
            "name": f"Questions about {moment_name}",
            "query": f"What were the key takeaways from {moment_name}?",
            "session_type": "chat",
            "created_at": now - timedelta(hours=2),
            "updated_at": now - timedelta(hours=2),
        },
        {
            "id": str(uuid4()),
            "tenant_id": tenant_id,
            "moment_id": moment_id,
            "name": f"Follow-up on {moment_name}",
            "query": f"Can you summarize the action items from {moment_name}?",
            "session_type": "chat",
            "created_at": now - timedelta(hours=1),
            "updated_at": now - timedelta(hours=1),
        },
    ]

    return sessions


async def initialize_tenant_sample_data(tenant_id: str) -> dict[str, Any]:
    """
    Initialize sample data for a new tenant.

    This function creates:
    - 5 sample moments with speakers, emotions, and images
    - 2 sample sessions per moment (10 total sessions)

    Args:
        tenant_id: The tenant ID to create sample data for

    Returns:
        Dictionary with counts of created entities

    Example:
        >>> result = await initialize_tenant_sample_data("tenant-123")
        >>> print(result)
        {
            "moments_created": 5,
            "sessions_created": 10,
            "moment_ids": ["id1", "id2", ...],
            "session_ids": ["sid1", "sid2", ...]
        }
    """
    from p8fs.repository import TenantRepository
    from p8fs.models.p8 import Moment, Session
    from p8fs_cluster.logging import get_logger

    logger = get_logger(__name__)

    try:
        # Create moments
        moments_data = create_sample_moments(tenant_id)
        moment_repo = TenantRepository(Moment, tenant_id=tenant_id)

        moment_ids = []
        for moment_data in moments_data:
            try:
                # Use put() instead of upsert() to trigger entity indexing in KV store
                moment = Moment(**moment_data)
                await moment_repo.put(moment)
                moment_ids.append(moment_data["id"])
                logger.info(f"Created sample moment: {moment_data['name']}")
            except Exception as e:
                logger.warning(f"Failed to create moment {moment_data['name']}: {e}")

        # Create sessions for each moment
        session_repo = TenantRepository(Session, tenant_id=tenant_id)
        session_ids = []

        for moment_data in moments_data:
            sessions_data = create_sample_sessions_for_moment(
                tenant_id=tenant_id,
                moment_id=moment_data["id"],
                moment_name=moment_data["name"],
            )

            for session_data in sessions_data:
                try:
                    # Use put() instead of upsert() to trigger entity indexing in KV store
                    session = Session(**session_data)
                    await session_repo.put(session)
                    session_ids.append(session_data["id"])
                    logger.info(f"Created sample session for moment: {moment_data['name']}")
                except Exception as e:
                    logger.warning(f"Failed to create session for moment {moment_data['name']}: {e}")

        logger.info(
            f"Sample data initialized for tenant {tenant_id}: "
            f"{len(moment_ids)} moments, {len(session_ids)} sessions"
        )

        return {
            "moments_created": len(moment_ids),
            "sessions_created": len(session_ids),
            "moment_ids": moment_ids,
            "session_ids": session_ids,
            "success": True,
        }

    except Exception as e:
        logger.error(f"Failed to initialize sample data for tenant {tenant_id}: {e}", exc_info=True)
        return {
            "moments_created": 0,
            "sessions_created": 0,
            "moment_ids": [],
            "session_ids": [],
            "success": False,
            "error": str(e),
        }
