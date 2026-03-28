"""Image generation service — create social media visuals via fal.ai."""

import structlog

from agency.config import get_settings

logger = structlog.get_logger()

PLATFORM_ASPECT_RATIOS = {
    "instagram": "square",
    "twitter": "landscape_16_9",
    "linkedin": "landscape_16_9",
    "facebook": "landscape_16_9",
    "tiktok": "portrait_16_9",
}


async def generate_social_image(
    prompt: str,
    platform: str = "twitter",
    style: str = "professional",
) -> dict:
    """Generate a social media image via fal.ai API.

    Returns dict with image_url or error message.
    In production, calls fal.ai's text-to-image API.
    """
    settings = get_settings()
    if not settings.fal_api_key:
        return {
            "status": "skipped",
            "message": "Image generation not configured. Set FAL_API_KEY.",
            "image_url": None,
        }

    aspect_ratio = PLATFORM_ASPECT_RATIOS.get(platform, "landscape_16_9")

    try:
        import httpx

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://queue.fal.run/fal-ai/flux/schnell",
                headers={
                    "Authorization": f"Key {settings.fal_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "prompt": f"{style} social media image: {prompt}",
                    "image_size": aspect_ratio,
                    "num_images": 1,
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                images = data.get("images", [])
                if images:
                    return {
                        "status": "generated",
                        "image_url": images[0].get("url", ""),
                        "platform": platform,
                    }
            return {
                "status": "error",
                "message": f"fal.ai returned {resp.status_code}",
                "image_url": None,
            }
    except Exception as e:
        logger.error("image_generation_failed", error=str(e))
        return {
            "status": "error",
            "message": str(e),
            "image_url": None,
        }
