"""Slack integration service — bot messaging and user mapping."""

import structlog

from agency.config import get_settings

logger = structlog.get_logger()


async def send_slack_message(channel: str, text: str) -> dict:
    """Send a message to a Slack channel."""
    settings = get_settings()
    if not settings.slack_bot_token:
        return {"error": "Slack not configured"}

    import httpx

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {settings.slack_bot_token}"},
            json={"channel": channel, "text": text},
        )
        return resp.json()


async def update_slack_message(channel: str, ts: str, text: str) -> dict:
    """Update an existing Slack message."""
    settings = get_settings()
    if not settings.slack_bot_token:
        return {"error": "Slack not configured"}

    import httpx

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://slack.com/api/chat.update",
            headers={"Authorization": f"Bearer {settings.slack_bot_token}"},
            json={"channel": channel, "ts": ts, "text": text},
        )
        return resp.json()
