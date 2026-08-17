"""Slack router — slash commands and event handling."""

import hashlib
import hmac
import json

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status

from agency.config import get_settings
from agency.dependencies import get_db
from agency.services.slack_integration import send_slack_message

logger = structlog.get_logger()

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


async def _require_slack_signature(request: Request, body: bytes) -> None:
    """Reject unsigned requests when a signing secret is configured.

    ``_verify_slack_signature`` existed but was never called, so both endpoints
    were fully unauthenticated. Enforcement is conditional on the secret being
    set so an unconfigured deployment keeps its current behaviour rather than
    breaking Slack's URL-verification handshake.
    """
    if not get_settings().slack_signing_secret:
        logger.warning("slack_request_unverified", reason="SLACK_SIGNING_SECRET not set")
        return
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")
    if not _verify_slack_signature(body, timestamp, signature):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid Slack signature")


@router.post("/events")
async def handle_slack_event(request: Request, db=Depends(get_db)):
    """Handle Slack event callbacks."""
    raw = await request.body()
    await _require_slack_signature(request, raw)
    body = json.loads(raw or b"{}")

    # URL verification challenge
    if body.get("type") == "url_verification":
        return {"challenge": body.get("challenge")}

    event = body.get("event", {})
    event_type = event.get("type", "")

    if event_type == "app_mention":
        channel = event.get("channel", "")
        await send_slack_message(
            channel,
            "Thanks for mentioning me! Campaigns are created in the CampaignForge "
            "dashboard — the Slack app cannot start a pipeline yet.",
        )

    return {"status": "ok"}


@router.post("/commands")
async def handle_slash_command(request: Request, db=Depends(get_db)):
    """Handle /campaignforge slash commands."""
    await _require_slack_signature(request, await request.body())
    form = await request.form()
    text = str(form.get("text", "")).strip()

    if not text:
        return {
            "response_type": "ephemeral",
            "text": "Usage: `/campaignforge create [campaign brief]` or `/campaignforge status`",
        }

    parts = text.split(" ", 1)
    action = parts[0].lower()

    if action == "create":
        # No Campaign row is created and no pipeline is started here — there is no
        # Slack→org mapping to authorise the write against. The old handler replied
        # "Creating campaign… I'll update you when it's ready!", which promised a
        # follow-up that could never arrive.
        return {
            "response_type": "ephemeral",
            "text": (
                "⚠️ Creating campaigns from Slack is not available yet. "
                "Create it in the CampaignForge dashboard instead — this command "
                "does not start a pipeline."
            ),
        }

    if action == "status":
        # Fixed string: this endpoint has no authenticated org context, so it
        # cannot report on any particular workspace's campaigns.
        return {
            "response_type": "ephemeral",
            "text": (
                "📊 The CampaignForge Slack app is reachable. Per-campaign status "
                "is only available in the dashboard."
            ),
        }

    return {
        "response_type": "ephemeral",
        "text": f"Unknown command: `{action}`. Try `create` or `status`.",
    }
