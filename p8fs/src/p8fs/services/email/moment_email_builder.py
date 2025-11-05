"""Moment email builder service for generating beautiful HTML emails from moment data."""

from datetime import datetime
from typing import Any, Literal

from p8fs_cluster.config.settings import config
from p8fs_cluster.logging import get_logger
from p8fs.models.engram.models import Moment
from p8fs.services.llm import MemoryProxy

logger = get_logger(__name__)

# Theme type
ThemeType = Literal["warm", "professional"]


class EmailTheme:
    """Email theme configuration with colors and styling."""

    def __init__(
        self,
        primary: str,
        secondary: str,
        background: str,
        light: str,
        fonts: str,
        name: str
    ):
        self.primary = primary
        self.secondary = secondary
        self.background = background
        self.light = light
        self.fonts = fonts
        self.name = name


# Available themes
THEMES = {
    "warm": EmailTheme(
        primary="#e74c3c",
        secondary="#c0392b",
        background="#fef5f4",
        light="#fadbd8",
        fonts="https://fonts.googleapis.com/css2?family=Spectral:wght@400;600;700&family=Cormorant+Garamond:wght@600;700&display=swap",
        name="Warm"
    ),
    "professional": EmailTheme(
        primary="#3498db",
        secondary="#2980b9",
        background="#ecf0f1",
        light="#e8f4f8",
        fonts="https://fonts.googleapis.com/css2?family=Lora:wght@400;600;700&family=Crimson+Text:wght@400;600&display=swap",
        name="Professional"
    )
}


class MomentEmailBuilder:
    """Builds beautiful HTML emails from moment data."""

    def __init__(self, llm_service: MemoryProxy | None = None, theme: ThemeType = "warm", icon_base_url: str | None = None):
        """
        Initialize moment email builder.

        Args:
            llm_service: Optional LLM service for generating summaries
            theme: Email theme to use ("warm" or "professional")
            icon_base_url: Base URL for icon images (defaults to config.api_base_url)
        """
        self.llm_service = llm_service
        self.theme = THEMES[theme]
        self.icon_base_url = icon_base_url or config.api_base_url

    def _get_moment_color_scheme(self, moment_type: str) -> dict[str, str]:
        """Get color scheme from current theme."""
        return {
            "primary": self.theme.primary,
            "secondary": self.theme.secondary,
            "background": self.theme.background,
            "light": self.theme.light
        }

    def _get_icon_url(self, icon_name: str) -> str:
        """Get URL for icon image."""
        return f"{self.icon_base_url}/icons/{icon_name}"

    def _get_mood_icon(self, emotion_tags: list[str]) -> str:
        """Get icon name for mood based on emotion tags."""
        mood_map = {
            "happy": "happy",
            "sad": "sad",
            "excited": "excited",
            "focused": "focused",
            "collaborative": "collaborative",
            "optimistic": "optimistic",
            "stressed": "stressed",
            "frustrated": "frustrated",
            "relieved": "relieved",
            "analytical": "analytical",
            "creative": "creative",
            "productive": "productive"
        }

        tag = emotion_tags[0].lower() if emotion_tags else "focused"
        return mood_map.get(tag, "focused")

    def _format_time(self, timestamp: datetime | None) -> str:
        """Format timestamp for display."""
        if not timestamp:
            return ""
        return timestamp.strftime("%I:%M %p")

    def _format_date(self, timestamp: datetime | None) -> str:
        """Format date for display."""
        if not timestamp:
            return ""
        return timestamp.strftime("%A, %B %d, %Y")

    def _format_participants(self, present_persons: dict[str, Any] | None, color: str) -> str:
        """Format participants HTML with hosted icon images."""
        if not present_persons:
            return ""

        icon_url = self._get_icon_url("user")
        participants_html = []
        for person_data in present_persons.values():
            user_label = person_data.get("user_label", "Unknown")
            participants_html.append(f'<span style="display: inline-flex; align-items: center; background-color: #ffffff; padding: 6px 12px; border-radius: 20px; font-size: 13px; color: #2c3e50; border: 1px solid #e8e8e8;"><img src="{icon_url}" width="16" height="16" style="margin-right: 6px;" alt="User" />{user_label}</span>')

        return f'<div style="background-color: #f8f9fa; padding: 14px 16px; border-radius: 6px; margin-bottom: 16px;"><p style="margin: 0 0 8px 0; color: #7f8c8d; font-size: 12px; font-weight: 600; letter-spacing: 0.5px; text-transform: uppercase;">Participants</p><div style="display: flex; gap: 12px; flex-wrap: wrap;">{" ".join(participants_html)}</div></div>'

    def _format_topics(self, topic_tags: list[str] | None, background_color: str, text_color: str) -> str:
        """Format topic tags HTML."""
        if not topic_tags:
            return ""

        tags_html = ''.join([
            f'<span style="display: inline-block; background-color: {background_color}; color: {text_color}; padding: 6px 12px; border-radius: 4px; font-size: 12px; font-weight: 600; margin-right: 8px; margin-bottom: 8px;">#{tag}</span>'
            for tag in topic_tags
        ])

        return f'<div style="display: block; line-height: 1.5;">{tags_html}</div>'

    def _format_location(self, location: str | None, background_sounds: str | None, background_color: str, primary_color: str, text_color: str) -> str:
        """Format location & environment HTML with hosted icon images."""
        if not location and not background_sounds:
            return ""

        location_html = ""
        sounds_html = ""

        if location:
            location_icon_url = self._get_icon_url("location")
            location_html = f'<div style="display: flex; align-items: center;"><img src="{location_icon_url}" width="18" height="18" style="margin-right: 10px;" alt="Location" /><span style="color: {text_color}; font-size: 13px; font-weight: 600;">{location}</span></div>'

        if background_sounds:
            music_icon_url = self._get_icon_url("music")
            sounds_html = f'<div style="display: flex; align-items: center;"><img src="{music_icon_url}" width="18" height="18" style="margin-right: 10px;" alt="Sounds" /><span style="color: {text_color}; font-size: 13px;">{background_sounds}</span></div>'

        return f'<div style="background-color: {background_color}; padding: 16px 20px; border-radius: 8px; margin-bottom: 20px;"><div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 14px;">{location_html}{sounds_html}</div></div>'

    def _build_mood_indicator(self, emotion_text: str, background_color: str, primary_color: str, secondary_color: str, emotion_tags: list[str] | None) -> str:
        """Build mood indicator HTML with multiple emotion states using hosted icons."""
        tags = emotion_tags or []
        if not tags:
            return ""

        # Build emotion items with separators using hosted icons
        emotion_items = []
        for i, tag in enumerate(tags):
            icon_name = self._get_mood_icon([tag])
            icon_url = self._get_icon_url(icon_name)
            emotion_items.append(f'<div style="display: flex; align-items: center;"><img src="{icon_url}" width="18" height="18" style="margin-right: 8px;" alt="{tag}" /><span style="color: {secondary_color}; font-size: 14px; font-weight: 700;">{tag.replace("-", " ").title()}</span></div>')

            # Add separator if not last item
            if i < len(tags) - 1:
                emotion_items.append(f'<div style="color: {secondary_color}; opacity: 0.3; font-size: 18px; padding: 0 6px;">•</div>')

        return f'<div style="background-color: {background_color}; padding: 16px 20px; border-radius: 8px; margin-bottom: 24px; border-left: 4px solid {primary_color};"><div style="display: flex; align-items: center; gap: 12px; flex-wrap: wrap;">{"".join(emotion_items)}</div></div>'

    def _build_summary_section(self, summary: str, background_color: str, light_color: str, secondary_color: str) -> str:
        """Build summary section HTML."""
        return f'''<div style="background: linear-gradient(135deg, {background_color} 0%, {light_color} 100%); padding: 20px 24px; border-radius: 8px; margin: 0 0 24px 0; border: 2px solid {light_color};">
                    <p style="margin: 0; color: {secondary_color}; font-size: 16px; line-height: 1.7; font-style: italic;">
                        {summary}
                    </p>
                </div>'''

    def build_moment_email_html(self, moment: Moment, date_title: str = "Your Moments") -> str:
        """
        Build beautiful HTML email from moment data using variant 4 template.

        Args:
            moment: Moment object with all the data
            date_title: Title for the email

        Returns:
            Complete HTML email string
        """
        colors = self._get_moment_color_scheme(moment.moment_type or "meeting")
        primary_color = colors["primary"]
        secondary_color = colors["secondary"]
        background_color = colors["background"]
        light_color = colors["light"]

        # Format emotion tags
        emotion_text = " · ".join(
            [tag.replace("-", " ").title() for tag in (moment.emotion_tags or [])]
        )

        # Build HTML
        html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{date_title} - {self._format_date(moment.resource_timestamp)}</title>
    <link href="{self.theme.fonts}" rel="stylesheet">
</head>
<body style="margin: 0; padding: 0; background-color: #f8fafb; font-family: 'Spectral', Georgia, serif;">
    <div style="max-width: 680px; margin: 40px auto; background-color: #ffffff; box-shadow: 0 2px 24px rgba(0,0,0,0.08);">
        <!-- Header -->
        <div style="background: linear-gradient(135deg, {secondary_color} 0%, {primary_color} 100%); padding: 40px 34px;">
            <div style="border-bottom: 2px solid rgba(255,255,255,0.25); padding-bottom: 18px;">
                <h1 style="margin: 0; color: #ffffff; font-family: 'Cormorant Garamond', serif; font-size: 38px; font-weight: 700; letter-spacing: -0.5px;">EEPIS Moments</h1>
                <p style="margin: 8px 0 0 0; color: rgba(255,255,255,0.88); font-size: 14px; letter-spacing: 1px; text-transform: uppercase;">{date_title}</p>
            </div>
        </div>

        <!-- Date Banner -->
        <div style="background-color: {light_color}; padding: 18px 34px; border-bottom: 1px solid {background_color};">
            <div style="display: flex; align-items: center; justify-content: space-between;">
                <p style="margin: 0; color: {secondary_color}; font-size: 15px; font-weight: 700;">{self._format_date(moment.resource_timestamp)}</p>
                <span style="color: {primary_color}; font-size: 14px; font-weight: 600;">{self._format_time(moment.resource_timestamp)}</span>
            </div>
        </div>

        <!-- Main Content -->
        <div style="padding: 40px 34px;">

            <!-- Moment Card -->
            <div style="background: #ffffff; border: 2px solid {light_color}; border-radius: 10px; padding: 32px; box-shadow: 0 4px 14px rgba(0,0,0,0.08);">
                <!-- Type Badge with Icon -->
                <div style="margin-bottom: 22px;">
                    <span style="display: inline-flex; align-items: center; background: linear-gradient(135deg, {primary_color} 0%, {secondary_color} 100%); color: white; padding: 8px 16px; border-radius: 6px; font-size: 12px; font-weight: 700; letter-spacing: 0.8px; text-transform: uppercase;">
                        <img src="{self._get_icon_url('memo')}" width="16" height="16" style="margin-right: 8px;" alt="Moment" />
                        {(moment.moment_type or "moment").replace("-", " ")}
                    </span>
                </div>

                <!-- Mood Indicator -->
                {self._build_mood_indicator(emotion_text, background_color, primary_color, secondary_color, moment.emotion_tags) if emotion_text else ''}

                <!-- Title -->
                <h2 style="margin: 0 0 16px 0; color: #2c1810; font-family: 'Cormorant Garamond', serif; font-size: 27px; font-weight: 700; line-height: 1.3;">{moment.name}</h2>

                <!-- Summary -->
                {self._build_summary_section(moment.summary, background_color, light_color, secondary_color) if moment.summary else ''}

                <!-- Full Content -->
                <p style="margin: 0 0 24px 0; color: #5a352a; font-size: 15px; line-height: 1.8;">
                    {moment.content}
                </p>

                <!-- Participants -->
                {self._format_participants(moment.present_persons, primary_color)}

                <!-- Location & Environment -->
                {self._format_location(moment.location, moment.background_sounds, background_color, primary_color, secondary_color)}

                <!-- Topics -->
                {self._format_topics(moment.topic_tags, light_color, secondary_color)}
            </div>

        </div>

        <!-- Footer -->
        <div style="background: linear-gradient(135deg, {secondary_color} 0%, {primary_color} 100%); padding: 34px; text-align: center;">
            <p style="margin: 0 0 10px 0; color: rgba(255,255,255,0.95); font-size: 13px; line-height: 1.7;">
                Every moment captured and remembered
            </p>
            <p style="margin: 0; color: rgba(255,255,255,0.75); font-size: 12px; letter-spacing: 0.8px;">
                EEPIS MOMENTS · YOUR INTELLIGENT COMPANION
            </p>
        </div>
    </div>
</body>
</html>'''

        return html

    async def build_with_llm_summary(
        self,
        moment: Moment,
        date_title: str = "Your Moments"
    ) -> str:
        """
        Build email with optional LLM-generated executive summary.

        Args:
            moment: Moment object
            date_title: Title for the email

        Returns:
            Complete HTML email string
        """
        if self.llm_service:
            try:
                # Generate enhanced summary with LLM
                from p8fs.services.llm.models import CallingContext

                prompt = f"""Provide a brief, insightful summary (2-3 sentences) of this moment:

Title: {moment.name}
Type: {moment.moment_type}
Content: {moment.content}

Focus on the key insights and value for the user."""

                context = CallingContext(
                    model="gpt-4o-mini",
                    temperature=0.7,
                    max_tokens=150
                )

                enhanced_summary = await self.llm_service.complete(prompt, context)

                # Update moment summary if LLM generated a good one
                if enhanced_summary and len(enhanced_summary) > 20:
                    moment.summary = enhanced_summary.strip()

            except Exception as e:
                logger.warning(f"Failed to generate LLM summary: {e}")

        return self.build_moment_email_html(moment, date_title)
