"""User-supplied URLs must only ever be fetched from the public internet.

DNS and HTTP are both mocked; these tests never touch the network.
"""

import httpx
import pytest

from agency.services import magic_brief, url_safety
from agency.services.url_safety import UnsafeURLError, assert_public_url, fetch_public_page

PUBLIC_IP = "93.184.215.14"


@pytest.fixture
def dns(monkeypatch):
    """Map hostnames to addresses; an unmapped name fails like a real NXDOMAIN."""
    table: dict[str, list[str]] = {}

    async def resolve(host: str, port: int) -> list[str]:
        if host in table:
            return table[host]
        raise url_safety.socket.gaierror(f"no such host: {host}")

    monkeypatch.setattr(url_safety, "_resolve", resolve)
    return table


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.5",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.169.254",  # cloud metadata
        "100.64.0.1",  # carrier-grade NAT
        "0.0.0.0",
        "::1",
        "fdaa::1",  # Fly.io private network
        "fe80::1",
        "::ffff:127.0.0.1",  # IPv4-mapped loopback
    ],
)
async def test_non_public_addresses_are_refused(dns, address):
    dns["brand.test"] = [address]
    with pytest.raises(UnsafeURLError, match="not a public website"):
        await assert_public_url("https://brand.test/")


async def test_one_private_address_among_public_ones_is_refused(dns):
    dns["brand.test"] = [PUBLIC_IP, "10.0.0.5"]
    with pytest.raises(UnsafeURLError):
        await assert_public_url("https://brand.test/")


async def test_public_address_is_allowed(dns):
    dns["brand.test"] = [PUBLIC_IP, "2606:2800:21f:cb07:6820:80da:af6b:8b2c"]
    await assert_public_url("https://brand.test/about")


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        ("file:///etc/passwd", "http and https"),
        ("ftp://brand.test/", "http and https"),
        ("gopher://brand.test/", "http and https"),
        ("https://user:pw@brand.test/", "username or password"),
        ("https://brand.test:8080/", "standard ports"),
        ("https://brand.test:99999/", "not a valid"),
        ("https:///path-only", "not a valid"),
    ],
)
async def test_malformed_or_non_web_urls_are_refused(dns, url, reason):
    dns["brand.test"] = [PUBLIC_IP]
    with pytest.raises(UnsafeURLError, match=reason):
        await assert_public_url(url)


async def test_unknown_host_is_refused_with_a_readable_reason(dns):
    with pytest.raises(UnsafeURLError, match="Could not find a website at nowhere.test"):
        await assert_public_url("https://nowhere.test/")


async def test_redirect_into_private_network_is_refused_before_it_is_requested(dns):
    dns["brand.test"] = [PUBLIC_IP]
    dns["metadata.test"] = ["169.254.169.254"]
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://metadata.test/latest/meta-data/"})

    async with _client(handler) as client:
        with pytest.raises(UnsafeURLError, match="not a public website"):
            await fetch_public_page("https://brand.test/", client)
    assert requested == ["https://brand.test/"]


async def test_relative_redirect_is_followed(dns):
    dns["brand.test"] = [PUBLIC_IP]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(301, headers={"location": "/en/"})
        return httpx.Response(200, text="<h1>Acme</h1>")

    async with _client(handler) as client:
        assert await fetch_public_page("https://brand.test/", client) == "<h1>Acme</h1>"


async def test_redirect_loop_is_cut_off(dns):
    dns["brand.test"] = [PUBLIC_IP]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "/again"})

    async with _client(handler) as client:
        with pytest.raises(UnsafeURLError, match="too many times"):
            await fetch_public_page("https://brand.test/", client)


async def test_oversized_page_is_truncated(dns):
    dns["brand.test"] = [PUBLIC_IP]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"a" * (url_safety.MAX_BYTES + 5000))

    async with _client(handler) as client:
        body = await fetch_public_page("https://brand.test/", client)
    assert len(body) == url_safety.MAX_BYTES


@pytest.mark.parametrize(
    "url", ["localhost", "localhost:8080", "http://127.0.0.1/admin", "169.254.169.254"]
)
async def test_magic_brief_refuses_internal_urls_without_calling_the_llm(monkeypatch, url):
    def no_llm(*args, **kwargs):
        raise AssertionError("the LLM must not be reached for a refused URL")

    monkeypatch.setattr(magic_brief, "get_worker_llm", no_llm)

    async def resolve(host: str, port: int) -> list[str]:
        return {"localhost": ["127.0.0.1"]}.get(host, [host])

    monkeypatch.setattr(url_safety, "_resolve", resolve)

    result = await magic_brief.extract_brand_from_url(url)
    assert result.get("error")
