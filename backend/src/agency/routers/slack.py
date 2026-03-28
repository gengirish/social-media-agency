"""Slack router — slash commands and event handling."""

import hashlib
import hmac

from fastapi import APIRouter, Depends, Request

from agency.config import get_settings
from agency.dependencies import get_db
from agency.services.slack_integration import send_slack_message

router = APIRouter(prefix="/integrations/slack", tags=["Slack"])


def _verify_slack_signature(body: bytes, timestamp: str, signature: str) -> bool:
    """Verify incoming Slack request signature."""
    settings = get_settings()
    if not settings.slack_signing_secret:
        return False
    sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
    my_sig = "v0=" + hmac.new(
        settings.slack_signing_secret.encode(),
        sig_basestring.encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(my_sig, signature)


@router.post("/events")
async def handle_slack_event(request: Request, db=Depends(get_db)):
    """Handle Slack event callbacks."""
    body = await request.json()

    # URL verification challenge
    if body.get("type") == "url_verification":
        return {"challenge": body.get("challenge")}

    event = body.get("event", {})
    event_type = event.get("type", "")

    if event_type == "app_mention":
        channel = event.get("channel", "")
        await send_slack_message(
            channel,
            "Thanks for mentioning me! Use `/campaignforge create [brief]` to create campaigns.",
        )

    return {"status": "ok"}


@router.post("/commands")
async def handle_slash_command(request: Request, db=Depends(get_db)):
    """Handle /campaignforge slash commands."""
    form = await request.form()
    text = form.get("text", "").strip()
    channel = form.get("channel_id", "")

    if not text:
        return {
            "response_type": "ephemeral",
            "text": "Usage: `/campaignforge create [campaign brief]` or `/campaignforge status`",
        }

    parts = text.split(" ", 1)
    action = parts[0].lower()

    if action == "create":
        brief = parts[1] if len(parts) > 1 else "Quick social campaign"
        await send_slack_message(
            channel,
            f"🚀 Creating campaign: *{brief}*\nI'll update you when it's ready!",
        )
        return {
            "response_type": "in_channel",
            "text": f"Campaign creation started: {brief}",
        }

    if action == "status":
        return {
            "response_type": "ephemeral",
            "text": "📊 CampaignForge is running. Use the dashboard for full status.",
        }

    return {
        "response_type": "ephemeral",
        "text": f"Unknown command: `{action}`. Try `create` or `status`.",
    }
