"""Collect the signals a page exposes: headers, cookies, HTML, DNS records (DoH) and TLS issuer."""
from __future__ import annotations

import asyncio
import re
import ssl
from urllib.parse import urljoin, urlsplit

import httpx

from .detector import PageSignals
from .netguard import assert_public_url

USER_AGENT = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36 TechDetector/1.0'
DOH = ('https://cloudflare-dns.com/dns-query', 'https://dns.google/resolve')
RT = {'NS': 2, 'CNAME': 5, 'SOA': 6, 'MX': 15, 'TXT': 16}
MAX_HTML = 3_000_000
DOMAIN_RE = re.compile(r'^(?=.{1,253}$)(?!-)([a-z0-9-]{1,63}(?<!-)\.)+[a-z]{2,63}$', re.I)


def normalize_target(raw: str) -> str:
    raw = (raw or '').strip()
    if not raw:
        raise ValueError('empty target')
    if '://' not in raw:
        raw = 'https://' + raw
    p = urlsplit(raw)
    if p.scheme not in ('http', 'https') or not p.hostname:
        raise ValueError(f'invalid URL: {raw!r}')
    if not DOMAIN_RE.match(p.hostname) and not re.match(r'^[\d.]+$', p.hostname):
        raise ValueError(f'invalid domain name: {p.hostname!r}')
    return f'{p.scheme}://{p.netloc.lower()}{p.path or "/"}' + (f'?{p.query}' if p.query else '')


def apex(host: str) -> str:
    parts = host.lower().split('.')
    if parts[0] == 'www':
        parts = parts[1:]
    if len(parts) >= 3 and parts[-2] in {'co', 'com', 'org', 'net', 'gov', 'ac', 'edu'} and len(parts[-1]) == 2:
        return '.'.join(parts[-3:])
    return '.'.join(parts[-2:])


async def doh(client: httpx.AsyncClient, name: str, rtype: str) -> list[str]:
    for ep in DOH:
        try:
            r = await client.get(ep, params={'name': name, 'type': rtype}, headers={'accept': 'application/dns-json'})
            if r.status_code == 200:
                return [str(a.get('data', '')).strip('"').rstrip('.') for a in r.json().get('Answer') or []
                        if a.get('type') == RT[rtype]]
        except (httpx.HTTPError, ValueError):
            continue
    return []


async def cert_issuer(host: str, timeout: float) -> str | None:
    try:
        ctx = ssl.create_default_context()
        _, w = await asyncio.wait_for(asyncio.open_connection(host, 443, ssl=ctx, server_hostname=host), timeout)
        cert = w.get_extra_info('ssl_object').getpeercert()
        w.close()
        issuer = dict(x[0] for x in cert.get('issuer', []))
        return issuer.get('organizationName') or issuer.get('commonName')
    except Exception:  # noqa: BLE001
        return None


async def collect(client: httpx.AsyncClient, target: str, *, timeout: float = 20, with_dns: bool = True,
                  allow_private: bool = False) -> tuple[PageSignals, dict]:
    url = normalize_target(target)
    current, chain = url, []
    cookies: dict[str, str] = {}
    for _ in range(10):
        await assert_public_url(current, allow_private=allow_private)
        resp = await client.get(current, follow_redirects=False)
        for k, v in resp.cookies.items():
            cookies[k.lower()] = v
        chain.append({'url': current, 'status': resp.status_code})
        if resp.is_redirect and 'location' in resp.headers:
            current = urljoin(current, resp.headers['location'])
            continue
        break
    else:
        raise RuntimeError('too many redirects')
    html = resp.text[:MAX_HTML] if 'html' in resp.headers.get('content-type', '') or resp.text.lstrip()[:1] == '<' else ''
    headers = {k.lower(): v for k, v in resp.headers.items()}
    final_host = urlsplit(current).hostname or ''
    dns: dict[str, list[str]] = {}
    issuer = None
    jobs = {}
    if with_dns and DOMAIN_RE.match(final_host):
        dom = apex(final_host)
        for rt in ('NS', 'MX', 'TXT', 'SOA'):
            jobs[rt] = doh(client, dom, rt)
        jobs['CNAME'] = doh(client, final_host, 'CNAME')
    if urlsplit(current).scheme == 'https' and not allow_private:
        jobs['cert'] = cert_issuer(final_host, timeout)
    if jobs:
        res = dict(zip(jobs, await asyncio.gather(*jobs.values())))
        issuer = res.pop('cert', None)
        dns = {k: v for k, v in res.items() if v}
    meta = {'finalUrl': current, 'status': resp.status_code, 'redirectChain': chain, 'certIssuer': issuer}
    return PageSignals(url=current, headers=headers, cookies=cookies, html=html, dns=dns, cert_issuer=issuer), meta
