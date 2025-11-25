"""Slack service for posting messages and files to Slack channels.

Slack Web API Integration
==========================

This service provides a lightweight wrapper around Slack's Web API for posting
messages and uploading files. It uses direct HTTP calls via httpx instead of
the official Slack SDK to minimize dependencies and maintain consistency with
P8FS patterns.

Official Documentation
---------------------
- Web API Overview: https://api.slack.com/web
- chat.postMessage: https://api.slack.com/methods/chat.postMessage
- files.upload: https://api.slack.com/methods/files.upload
- chat.update: https://api.slack.com/methods/chat.update

Authentication
--------------
The service uses bot token authentication (xoxb-*) which is configured via:
- P8FS_SLACK_BOT_TOKEN or SLACK_BOT_TOKEN environment variables
- Tokens are passed as Bearer tokens in the Authorization header
- Each workspace requires a separate bot token from a Slack app

How It Works
------------
1. **Message Posting**: Uses chat.postMessage to send text to channels
   - Supports threading via thread_ts parameter
   - Rate limited to ~1 message/second per channel
   - Supports Slack's mrkdwn formatting (similar to Markdown)

2. **File Uploads**: Uses files.upload (v2 API) for file sharing
   - Accepts raw bytes with filename
   - Can post to multiple channels simultaneously
   - Supports initial comments and threading
   - Returns file metadata including permalink

3. **Message Updates**: Uses chat.update to modify existing messages
   - Requires original message timestamp (ts)
   - Useful for progress updates and status messages
   - Supports Block Kit for rich formatting

4. **S3 Integration**: Download from S3 and upload to Slack
   - Leverages existing S3StorageService
   - Useful for sharing uploaded files with teams

Example Usage
-------------
```python
from p8fs.services.slack import SlackService

slack = SlackService()

# Post a simple message
response = await slack.post_message(
    message="Processing complete!",
    channel="#general",
    use_markdown=True
)

# Reply in a thread
thread_ts = response.get("ts")
await slack.post_message(
    message="Details: Everything succeeded",
    channel="#general",
    thread_ts=thread_ts
)

# Upload a file
with open("report.pdf", "rb") as f:
    await slack.post_file(
        data=f.read(),
        filename="report.pdf",
        channel="#reports",
        initial_comment="Here's the weekly report"
    )

# Update progress message
msg = await slack.post_message("Processing...", "#general")
# ... do work ...
await slack.update_message(
    message="Processing complete!",
    channel="#general",
    timestamp=msg["ts"]
)
```

Rate Limits
-----------
- chat.postMessage: ~1 message/second per channel (Tier 3)
- files.upload: ~20 uploads/minute (Tier 2)
- chat.update: ~50 updates/minute (Tier 3)

See: https://api.slack.com/docs/rate-limits

Configuration
-------------
Set environment variables:
```bash
export P8FS_SLACK_BOT_TOKEN=xoxb-your-bot-token-here
export P8FS_SLACK_APP_TOKEN=xapp-your-app-token-here  # For Socket Mode
export P8FS_SLACK_ENABLED=true
```

Or use Slack's standard variable names:
```bash
export SLACK_BOT_TOKEN=xoxb-your-bot-token-here
```

Security Notes
--------------
- Never commit tokens to version control
- Use workspace-specific bot tokens, not user tokens
- Rotate tokens periodically
- Monitor usage in Slack App settings
"""

from pathlib import Path
from typing import Any, Optional

import httpx
from p8fs_cluster.config.settings import config
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)


class SlackService:
    """Service for Slack operations with bot token authentication."""

    def __init__(
        self,
        bot_token: Optional[str] = None,
        app_token: Optional[str] = None,
    ):
        """
        Initialize Slack service.

        Args:
            bot_token: Slack bot token (defaults to config.slack_bot_token)
            app_token: Slack app token (defaults to config.slack_app_token)
        """
        self.bot_token = bot_token or config.slack_bot_token
        self.app_token = app_token or config.slack_app_token
        self.base_url = "https://slack.com/api"

        if not self.bot_token:
            logger.warning("Slack bot token not configured - service will not function")

    def _get_headers(self) -> dict[str, str]:
        """Build headers for Slack API requests."""
        return {
            "Authorization": f"Bearer {self.bot_token}",
            "Content-Type": "application/json",
        }

    async def post_message(
        self,
        message: str,
        channel: str,
        thread_ts: Optional[str] = None,
        use_markdown: bool = False,
    ) -> dict[str, Any]:
        """
        Post a message to a Slack channel.

        Args:
            message: Message text to post
            channel: Channel ID or name (e.g., "C1234567890" or "#general")
            thread_ts: Thread timestamp for replying in a thread
            use_markdown: Enable markdown formatting (mrkdwn)

        Returns:
            Slack API response with message metadata

        Example:
            response = await slack.post_message(
                message="Hello from P8FS!",
                channel="#general",
                use_markdown=True
            )
            thread_ts = response.get("ts")  # Use for threading
        """
        url = f"{self.base_url}/chat.postMessage"

        payload = {
            "channel": channel,
            "text": str(message),
            "mrkdwn": use_markdown,
        }

        if thread_ts:
            payload["thread_ts"] = thread_ts

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                headers=self._get_headers(),
                json=payload,
            )

        if response.status_code != 200:
            raise RuntimeError(
                f"Failed to post message: {response.status_code} - {response.text}"
            )

        result = response.json()
        if not result.get("ok"):
            raise RuntimeError(f"Slack API error: {result.get('error', 'Unknown error')}")

        logger.info(f"Posted message to channel {channel}")
        return result

    async def update_message(
        self,
        message: str,
        channel: str,
        timestamp: str,
        blocks: Optional[dict] = None,
    ) -> dict[str, Any]:
        """
        Update an existing message.

        Args:
            message: New message text
            channel: Channel ID or name
            timestamp: Message timestamp (from original post_message response)
            blocks: Optional block kit formatting

        Returns:
            Slack API response
        """
        url = f"{self.base_url}/chat.update"

        payload = {
            "channel": channel,
            "ts": timestamp,
            "text": str(message),
        }

        if blocks:
            payload["blocks"] = blocks

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                headers=self._get_headers(),
                json=payload,
            )

        if response.status_code != 200:
            raise RuntimeError(
                f"Failed to update message: {response.status_code} - {response.text}"
            )

        result = response.json()
        if not result.get("ok"):
            raise RuntimeError(f"Slack API error: {result.get('error', 'Unknown error')}")

        logger.info(f"Updated message in channel {channel}")
        return result

    async def post_file(
        self,
        data: bytes,
        filename: str,
        channel: str,
        thread_ts: Optional[str] = None,
        initial_comment: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Post a file to a Slack channel.

        Args:
            data: File bytes
            filename: Name for the uploaded file
            channel: Channel ID or name
            thread_ts: Thread timestamp for posting in a thread
            initial_comment: Optional message to accompany the file

        Returns:
            Slack API response
        """
        url = f"{self.base_url}/files.upload"

        headers = {
            "Authorization": f"Bearer {self.bot_token}",
        }

        files = {
            "file": (filename, data),
        }

        data_payload = {
            "channels": channel,
        }

        if thread_ts:
            data_payload["thread_ts"] = thread_ts

        if initial_comment:
            data_payload["initial_comment"] = initial_comment

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                url,
                headers=headers,
                files=files,
                data=data_payload,
            )

        if response.status_code != 200:
            raise RuntimeError(
                f"Failed to upload file: {response.status_code} - {response.text}"
            )

        result = response.json()
        if not result.get("ok"):
            raise RuntimeError(f"Slack API error: {result.get('error', 'Unknown error')}")

        logger.info(f"Uploaded file {filename} to channel {channel}")
        return result

    async def post_files(
        self,
        files: list[dict[str, Any]],
        channel: str,
        thread_ts: Optional[str] = None,
        initial_comment: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Post multiple files to a Slack channel.

        Args:
            files: List of file dicts with 'file' (bytes) and 'filename' (str) keys
            channel: Channel ID or name
            thread_ts: Thread timestamp for posting in a thread
            initial_comment: Optional message to accompany the files

        Returns:
            Slack API response

        Example:
            await slack.post_files(
                files=[
                    {"file": b"content1", "filename": "file1.txt"},
                    {"file": b"content2", "filename": "file2.txt"},
                ],
                channel="#general",
                initial_comment="Here are the files"
            )
        """
        url = f"{self.base_url}/files.upload"

        headers = {
            "Authorization": f"Bearer {self.bot_token}",
        }

        file_uploads = [
            (filename, file_data) for f in files
            for filename, file_data in [(f["filename"], f["file"])]
        ]

        data_payload = {
            "channels": channel,
        }

        if thread_ts:
            data_payload["thread_ts"] = thread_ts

        if initial_comment:
            data_payload["initial_comment"] = initial_comment

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                url,
                headers=headers,
                files=[("file", f) for f in file_uploads],
                data=data_payload,
            )

        if response.status_code != 200:
            raise RuntimeError(
                f"Failed to upload files: {response.status_code} - {response.text}"
            )

        result = response.json()
        if not result.get("ok"):
            raise RuntimeError(f"Slack API error: {result.get('error', 'Unknown error')}")

        logger.info(f"Uploaded {len(files)} files to channel {channel}")
        return result

    async def post_s3_file(
        self,
        s3_path: str,
        channel: str,
        thread_ts: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Post a file from S3 storage to a Slack channel.

        Args:
            s3_path: S3 file path
            channel: Channel ID or name
            thread_ts: Thread timestamp for posting in a thread
            tenant_id: Tenant ID for S3 storage (defaults to config.default_tenant_id)

        Returns:
            Slack API response
        """
        from p8fs.services.s3_storage import S3StorageService

        tenant_id = tenant_id or config.default_tenant_id
        s3_service = S3StorageService()

        file_data = await s3_service.download_file(s3_path, tenant_id)
        if not file_data:
            raise RuntimeError(f"File not found in S3: {s3_path}")

        filename = Path(s3_path).name
        return await self.post_file(
            data=file_data["content"],
            filename=filename,
            channel=channel,
            thread_ts=thread_ts,
        )

    async def get_channel_id(self, channel_name: str) -> Optional[str]:
        """
        Get channel ID from channel name.

        Args:
            channel_name: Channel name (with or without # prefix)

        Returns:
            Channel ID or None if not found

        TODO: Implement channel lookup with pagination
        """
        logger.warning("get_channel_id not yet implemented - returning None")
        return None

    async def get_channel_name(self, channel_id: str) -> Optional[str]:
        """
        Get channel name from channel ID.

        Args:
            channel_id: Channel ID

        Returns:
            Channel name or None if not found

        TODO: Implement channel info lookup
        """
        logger.warning("get_channel_name not yet implemented - returning None")
        return None

    async def load_channels(self) -> list[dict[str, Any]]:
        """
        Load all channels accessible to the bot.

        Returns:
            List of channel dicts with id, name, description, num_members

        TODO: Implement channel listing with pagination
        """
        logger.warning("load_channels not yet implemented - returning empty list")
        return []

    async def load_users(self) -> list[dict[str, Any]]:
        """
        Load all users in the workspace.

        Returns:
            List of user dicts with id, name, full_name, email

        TODO: Implement user listing with pagination
        """
        logger.warning("load_users not yet implemented - returning empty list")
        return []

    async def retrieve_thread(
        self,
        channel_id: str,
        thread_ts: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Retrieve messages from a thread.

        Args:
            channel_id: Channel ID
            thread_ts: Thread timestamp
            limit: Maximum messages to retrieve

        Returns:
            List of message dicts

        TODO: Implement thread retrieval with pagination
        """
        logger.warning("retrieve_thread not yet implemented - returning empty list")
        return []

    async def process_messages(
        self,
        channel_id: str,
        oldest: Optional[str] = None,
        latest: Optional[str] = None,
        batch_size: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Process messages from a channel within a time window.

        Args:
            channel_id: Channel ID
            oldest: Oldest timestamp (Unix timestamp or ISO format)
            latest: Latest timestamp (Unix timestamp or ISO format)
            batch_size: Number of messages to retrieve per batch

        Returns:
            List of processed message dicts

        TODO: Implement message processing with time windows
        """
        logger.warning("process_messages not yet implemented - returning empty list")
        return []
