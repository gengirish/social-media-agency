"""Server-side fetches of URLs a user typed, restricted to the public internet.

Anything that fetches a caller-supplied URL from inside Fly can otherwise be
pointed at ``localhost``, the ``fdaa::/16`` private network, or a link-local
metadata address — and a public URL can *redirect* there, so redirects are
followed by hand and every hop is checked, never left to httpx.

What this does not close: DNS rebinding. The name is resolved here and again by
httpx when it connects, so a hostile resolver could answer differently the
second time. Pinning the connection to the checked IP would close it, at the
cost of a custom transport; the window is small and nothing here is sent back
raw — the page only feeds an LLM prompt.
"""

import asyncio
import ipaddress
import socket
from urllib.parse import urljoin, urlsplit

import httpx

ALLOWED_SCHEMES = frozenset({"http", "https"})
# Brand websites live on the default ports; anything else is far more likely an
# internal service than a homepage.
ALLOWED_PORTS = frozenset({80, 443})
MAX_REDIRECTS = 5
# Past this the page is truncated, not refused: the text worth reading is near
# the top, and the caller keeps only a few thousand characters anyway.
MAX_BYTES = 2_000_000
USER_AGENT = "CampaignForge Bot/1.0"


class UnsafeURLError(ValueError):
    """The URL points somewhere the server must not fetch. Safe to show the user."""


async def _resolve(host: str, port: int) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [str(info[4][0]) for info in infos]


def _is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%", 1)[0])
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def assert_safe_link(url: str) -> str:
    """Check a URL the *browser* will open, and return it stripped.

    For a link rendered with ``target="_blank"`` the danger is the scheme —
    ``javascript:``, ``data:``, ``file:`` — not where the name resolves: the
    server never fetches it, so there is no SSRF to close and no reason to make a
    DNS lookup part of a write request. A loopback or private *literal* and
    ``localhost`` are still refused, since neither is a page a colleague could open.
    This is the shape check that :func:`assert_public_url` also performs before it
    resolves anything, so the two cannot disagree about what a URL even is.

    Raises :class:`UnsafeURLError`, whose message is safe to show the user.
    """
    url = url.strip()
    if not url:
        raise UnsafeURLError("That is not a valid website address")
    parts = urlsplit(url)
    if parts.scheme not in ALLOWED_SCHEMES:
        raise UnsafeURLError("Only http and https links are allowed")
    if parts.username or parts.password:
        raise UnsafeURLError("Website addresses with a username or password are not supported")
    if not parts.hostname:
        raise UnsafeURLError("That is not a valid website address")
    try:
        port = parts.port
    except ValueError as e:
        raise UnsafeURLError("That is not a valid website address") from e
    if port is not None and port not in ALLOWED_PORTS:
        raise UnsafeURLError("Only websites on the standard ports (80 and 443) can be read")
    # A literal address or ``localhost`` is refused here without resolving anything: it
    # is not a page anyone else can open, so it is junk in a shared workspace whichever
    # way you read it. Only names are left to ``assert_public_url``, which resolves.
    host = parts.hostname
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None and not _is_public(host):
        raise UnsafeURLError("That address is not a public website")
    if host == "localhost" or host.endswith((".localhost", ".local")):
        raise UnsafeURLError("That address is not a public website")
    return url


async def assert_public_url(url: str) -> None:
    """Raise :class:`UnsafeURLError` unless every address ``url`` resolves to is public."""
    url = assert_safe_link(url)
    parts = urlsplit(url)
    # Non-empty: ``assert_safe_link`` rejects a URL with no host.
    host = parts.hostname or ""
    port = parts.port
    try:
        addresses = await _resolve(host, port or (443 if parts.scheme == "https" else 80))
    except (socket.gaierror, UnicodeError) as e:
        raise UnsafeURLError(f"Could not find a website at {host}") from e
    # Every address, not just the first: httpx may connect to any of them.
    if not addresses or not all(_is_public(a) for a in addresses):
        raise UnsafeURLError("That address is not a public website")


async def fetch_public_page(url: str, client: httpx.AsyncClient) -> str:
    """GET ``url`` and return its body as text, checking every redirect hop.

    ``client`` must not follow redirects itself (httpx's default).
    """
    for _ in range(MAX_REDIRECTS + 1):
        await assert_public_url(url)
        async with client.stream(
            "GET", url, headers={"User-Agent": USER_AGENT}, follow_redirects=False
        ) as resp:
            if resp.is_redirect:
                location = resp.headers.get("location")
                if not location:
                    raise UnsafeURLError("The website sent a redirect with no destination")
                url = urljoin(url, location)
                continue
            resp.raise_for_status()
            body = bytearray()
            async for chunk in resp.aiter_bytes():
                body += chunk
                if len(body) >= MAX_BYTES:
                    break
            return bytes(body[:MAX_BYTES]).decode(resp.encoding or "utf-8", errors="replace")
    raise UnsafeURLError("The website redirected too many times")
