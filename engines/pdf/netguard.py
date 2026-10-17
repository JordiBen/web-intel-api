"""Small SSRF guard: refuse to fetch private, loopback, link-local or reserved addresses."""
from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit


class BlockedAddressError(ValueError):
    pass


def _is_public(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return not (addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_multicast
                or addr.is_reserved or addr.is_unspecified)


async def assert_public_host(host: str, *, allow_private: bool = False) -> list[str]:
    """Resolve host and raise BlockedAddressError if any address is not public."""
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    ips = sorted({i[4][0] for i in infos})
    if not allow_private:
        bad = [ip for ip in ips if not _is_public(ip)]
        if bad:
            raise BlockedAddressError(f'{host} resolves to non-public address {bad[0]}')
    return ips


async def assert_public_url(url: str, *, allow_private: bool = False) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ('http', 'https'):
        raise BlockedAddressError(f'Unsupported scheme: {parts.scheme!r}')
    if not parts.hostname:
        raise BlockedAddressError('URL has no host')
    await assert_public_host(parts.hostname, allow_private=allow_private)
