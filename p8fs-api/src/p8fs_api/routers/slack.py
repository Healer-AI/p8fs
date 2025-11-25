"""Slack webhook router for receiving and processing Slack events.

Slack Events API Integration
=============================

This router implements Slack's Events API webhook receiver, allowing P8FS to
receive real-time events from Slack workspaces (messages, reactions, app mentions,
etc.). It handles signature verification, URL verification, and asynchronous event
processing following Slack's best practices.

Official Documentation
---------------------
- Events API Overview: https://api.slack.com/events-api
- Events API Types: https://api.slack.com/events
- Request Verification: https://api.slack.com/authentication/verifying-requests-from-slack
- Slash Commands: https://api.slack.com/interactivity/slash-commands
- Interactive Components: https://api.slack.com/interactivity/handling

How the Events API Works
------------------------

1. **Subscription Setup**: In your Slack app settings, you configure:
   - Event subscriptions (which events you want to receive)
   - Request URL (where Slack sends events): https://your-domain/api/v1/slack/events
   - Bot token scopes (permissions your app needs)

2. **URL Verification**: First time setup, Slack sends a challenge:
   ```json
   {
     "token": "verification_token",
     "challenge": "3eZbrw1aBm2rZgRNFdxV2595E9CY3gmdALWMmHkvFXO7tYXAYM8P",
     "type": "url_verification"
   }
   ```
   Your endpoint must return: `{"challenge": "3eZbrw1aBm2rZgRNFdxV2595E9CY3gmdALWMmHkvFXO7tYXAYM8P"}`

3. **Event Delivery**: After verification, Slack sends events as HTTP POST:
   ```json
   {
     "token": "verification_token",
     "team_id": "T1234567890",
     "api_app_id": "A1234567890",
     "event": {
       "type": "message",
       "channel": "C2147483705",
       "user": "U2147483697",
       "text": "Hello world",
       "ts": "1355517523.000005"
     },
     "type": "event_callback",
     "event_id": "Ev1234567890",
     "event_time": 1234567890
   }
   ```

4. **Response**: Your endpoint MUST respond with HTTP 200 within 3 seconds:
   - Return `{"status": "ok"}` immediately
   - Process events asynchronously in background tasks
   - Slack retries if no 200 received (with exponential backoff)

Request Signature Verification
-------------------------------

Slack signs each request with HMAC-SHA256 for security. To verify:

1. Extract headers:
   - `X-Slack-Request-Timestamp`: Unix timestamp
   - `X-Slack-Signature`: HMAC signature (format: v0=hash)

2. Check timestamp is recent (within 5 minutes) to prevent replay attacks

3. Compute signature:
   ```python
   sig_basestring = f"v0:{timestamp}:{raw_body}"
   my_signature = "v0=" + hmac.new(
       signing_secret.encode(),
       sig_basestring.encode(),
       hashlib.sha256
   ).hexdigest()
   ```

4. Compare using constant-time comparison:
   ```python
   hmac.compare_digest(my_signature, slack_signature)
   ```

IMPORTANT: Use the raw request body (preserve whitespace) for signature verification.
See: https://api.slack.com/authentication/verifying-requests-from-slack

Event Processing Pattern
------------------------

To avoid Slack's 3-second timeout, events are processed asynchronously:

1. Verify signature
2. Handle URL verification challenge (if needed)
3. Extract event payload
4. Queue event for background processing
5. Return HTTP 200 immediately
6. Process event in background task:
   - Filter bot messages (avoid loops)
   - Route to appropriate handlers
   - Call Slack API to respond
   - Store data in database

Example Event Flow
------------------

User posts in Slack:
  → Slack sends webhook POST
    → Router verifies signature
      → Router queues background task
        → Router returns 200 OK
          → Background task processes event
            → SlackService posts response
              → Database stores interaction

Common Event Types
------------------
- `message`: New message in channel/DM
- `app_mention`: Bot mentioned with @botname
- `reaction_added`: Emoji reaction added
- `member_joined_channel`: User joined channel
- `file_shared`: File uploaded to channel

Full list: https://api.slack.com/events

Configuration
-------------

1. Create Slack app: https://api.slack.com/apps
2. Enable Events API and set request URL
3. Subscribe to bot events (message.channels, app_mention, etc.)
4. Install app to workspace to get bot token
5. Set environment variables:
   ```bash
   export P8FS_SLACK_BOT_TOKEN=xoxb-your-bot-token
   export P8FS_SLACK_APP_TOKEN=xapp-your-app-token  # For Socket Mode
   export P8FS_SLACK_SIGNING_SECRET=your-signing-secret
   export P8FS_SLACK_ENABLED=true
   ```

6. Configure OAuth scopes (bot token scopes):
   - chat:write - Post messages
   - files:write - Upload files
   - channels:history - Read channel messages
   - channels:read - List channels
   - users:read - Get user info

Slash Commands
--------------

Slash commands allow users to trigger actions with `/command` syntax:
- Endpoint: POST /api/v1/slack/commands/{command}
- Must respond within 3 seconds (use background tasks)
- Can respond ephemerally (only user sees) or in-channel

Interactive Components
----------------------

Handle button clicks, menu selections, modal submissions:
- Endpoint: POST /api/v1/slack/actions
- Requires signature verification
- Must respond within 3 seconds
- Can update original message or open modals

Rate Limits & Retries
---------------------

- Slack retries failed deliveries with exponential backoff
- Same event_id may be delivered multiple times (implement idempotency)
- Return 200 even if processing fails (avoid retry storms)
- Max 30,000 events/hour per app

Troubleshooting
---------------

- 401 errors: Check signature verification implementation
- Timeout errors: Ensure background processing, quick 200 response
- No events received: Check app installation and event subscriptions
- Duplicate events: Implement idempotency using event_id

Security Best Practices
-----------------------

- Always verify request signatures
- Never expose signing secret in logs or errors
- Check timestamp to prevent replay attacks
- Filter bot messages to prevent loops
- Validate channel/user permissions before responding
- Rate limit responses to prevent abuse

Socket Mode Alternative
-----------------------

For development or firewall restrictions, use Socket Mode instead of webhooks:
- Requires SLACK_APP_TOKEN (xapp-*)
- WebSocket connection instead of HTTP webhooks
- No need for public URL
- Handled by Slack SDK (not implemented in this minimal router)

See: https://api.slack.com/apis/connections/socket
"""

import hashlib
import hmac
import time
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from p8fs_cluster.config.settings import config
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/slack", tags=["Slack"])


def verify_slack_signature(
    signing_secret: str,
    timestamp: str,
    body: bytes,
    signature: str,
) -> bool:
    """
    Verify Slack request signature.

    Args:
        signing_secret: Slack signing secret
        timestamp: Request timestamp from headers
        body: Raw request body
        signature: Slack signature from headers

    Returns:
        True if signature is valid
    """
    if not signing_secret:
        logger.warning("Slack signing secret not configured - skipping verification")
        return True

    if abs(time.time() - int(timestamp)) > 60 * 5:
        logger.warning("Slack request timestamp too old")
        return False

    sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
    computed_signature = "v0=" + hmac.new(
        signing_secret.encode(),
        sig_basestring.encode(),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(computed_signature, signature)


@router.post("/events", include_in_schema=False)
async def slack_events(request: Request, background_tasks: BackgroundTasks) -> dict[str, Any]:
    """
    Handle Slack event callbacks.

    Receives events from Slack (messages, reactions, etc.) and processes them.
    Includes signature verification for security.

    Returns:
        Response dict
    """
    body = await request.body()
    headers = request.headers

    timestamp = headers.get("X-Slack-Request-Timestamp", "")
    signature = headers.get("X-Slack-Signature", "")

    if config.slack_signing_secret and not verify_slack_signature(
        config.slack_signing_secret,
        timestamp,
        body,
        signature,
    ):
        logger.warning("Invalid Slack signature")
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()

    if payload.get("type") == "url_verification":
        logger.info("Handling Slack URL verification")
        return {"challenge": payload.get("challenge")}

    event = payload.get("event", {})
    event_type = event.get("type")

    logger.info(f"Received Slack event: {event_type}")

    background_tasks.add_task(process_slack_event, event)

    return {"status": "ok"}


async def process_slack_event(event: dict[str, Any]) -> None:
    """
    Process Slack event.

    Args:
        event: Slack event payload

    TODO: Implement actual event processing
        - Route to appropriate handlers
        - Store messages in database
        - Trigger AI processing
        - Send responses via Slack service
    """
    if event.get("bot_id") or not event.get("text"):
        logger.debug("Ignoring bot message or message without text")
        return

    event_type = event.get("type")
    channel = event.get("channel")
    user = event.get("user")
    text = event.get("text")
    thread_ts = event.get("thread_ts")
    ts = event.get("ts")

    logger.info(
        f"Processing Slack event: type={event_type}, channel={channel}, "
        f"user={user}, thread_ts={thread_ts}, ts={ts}"
    )

    if event_type == "message":
        logger.debug(f"Message text: {text}")

    logger.warning("Slack event processing not yet implemented - event ignored")


@router.post("/commands/{command}", include_in_schema=False)
async def slack_command(command: str, request: Request) -> dict[str, Any]:
    """
    Handle Slack slash commands.

    Args:
        command: Command name (e.g., "search", "query")
        request: FastAPI request

    Returns:
        Response dict

    TODO: Implement slash command handlers
        - /search <query> - Semantic search
        - /query <rem_query> - REM query
        - /chat <message> - Chat with AI
    """
    form_data = await request.form()

    logger.info(f"Received Slack command: /{command}")
    logger.debug(f"Form data: {dict(form_data)}")

    return {
        "response_type": "ephemeral",
        "text": f"Command /{command} received but not yet implemented",
    }


@router.post("/actions", include_in_schema=False)
async def slack_actions(request: Request) -> dict[str, Any]:
    """
    Handle Slack interactive components (buttons, menus, etc.).

    Returns:
        Response dict

    TODO: Implement action handlers
        - Button clicks
        - Menu selections
        - Modal submissions
    """
    body = await request.body()
    headers = request.headers

    timestamp = headers.get("X-Slack-Request-Timestamp", "")
    signature = headers.get("X-Slack-Signature", "")

    if config.slack_signing_secret and not verify_slack_signature(
        config.slack_signing_secret,
        timestamp,
        body,
        signature,
    ):
        logger.warning("Invalid Slack signature")
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()

    logger.info("Received Slack action")
    logger.debug(f"Action payload: {payload}")

    return {"status": "ok"}
