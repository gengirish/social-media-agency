"""Image generation tests.

All outbound HTTP goes through ``httpx.MockTransport`` via the
``_build_client`` seam, so these run without a ``FAL_API_KEY``.

The regression that matters here is ``test_200_without_images_reports_shape_change``:
the service used to POST to ``queue.fal.run``, which answers 200 with
``{"request_id", "status_url"}`` and never ``{"images": [...]}``. The parser
could not match, so every call returned ``"fal.ai returned 200"`` — identical to
a transport failure, which is why a permanently broken feature read as a
configuration problem for weeks.
"""

import httpx
import pytest

from agency.services import image_generation


@pytest.fixture
def fal_key(monkeypatch):
    """Give the service a non-blank key so it attempts the call."""
    settings = image_generation.get_settings()
    monkeypatch.setattr(settings, "fal_api_key", "test-key", raising=False)
    return settings


def _mock_client(handler):
    def build():
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    return build


async def test_success_returns_image_url(monkeypatch, fal_key):
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"images": [{"url": "https://cdn/img.png"}]})

    monkeypatch.setattr(image_generation, "_build_client", _mock_client(handler))

    result = await image_generation.generate_social_image("a cat", platform="linkedin")

    assert result["status"] == "generated"
    assert result["image_url"] == "https://cdn/img.png"
    assert result["platform"] == "linkedin"


async def test_calls_the_sync_endpoint_not_the_queue(monkeypatch, fal_key):
    """The queue endpoint can never return images. Pin the host."""
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"images": [{"url": "https://cdn/img.png"}]})

    monkeypatch.setattr(image_generation, "_build_client", _mock_client(handler))
    await image_generation.generate_social_image("a cat")

    assert seen["url"].startswith("https://fal.run/")
    assert "queue.fal.run" not in seen["url"]


async def test_200_without_images_reports_shape_change(monkeypatch, fal_key):
    """The exact response the old queue endpoint gave.

    Must be distinguishable from an HTTP failure, or the next protocol change is
    equally invisible.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"request_id": "abc", "status_url": "https://q/abc"})

    monkeypatch.setattr(image_generation, "_build_client", _mock_client(handler))

    result = await image_generation.generate_social_image("a cat")

    assert result["status"] == "error"
    assert result["image_url"] is None
    assert "response shape" in result["message"]
    # Must NOT collapse into the generic transport message.
    assert result["message"] != "fal.ai returned 200"


async def test_http_error_reports_status_code(monkeypatch, fal_key):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "boom"})

    monkeypatch.setattr(image_generation, "_build_client", _mock_client(handler))

    result = await image_generation.generate_social_image("a cat")

    assert result["status"] == "error"
    assert result["message"] == "fal.ai returned 500"
    assert result["image_url"] is None


async def test_blank_key_skips_without_calling(monkeypatch):
    settings = image_generation.get_settings()
    monkeypatch.setattr(settings, "fal_api_key", "", raising=False)

    called = False

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        nonlocal called
        called = True
        return httpx.Response(200, json={})

    monkeypatch.setattr(image_generation, "_build_client", _mock_client(handler))

    result = await image_generation.generate_social_image("a cat")

    assert result["status"] == "skipped"
    assert result["image_url"] is None
    assert called is False
