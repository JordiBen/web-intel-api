"""Core audit logic for one website/domain. Pure functions + async probes, no Apify dependency."""
from __future__ import annotations

import asyncio
import datetime as dt
import ipaddress
import re
import socket
import ssl
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

from .netguard import BlockedAddressError, assert_public_url

USER_AGENT = 'Mozilla/5.0 (compatible; WebsiteHealthAudit/1.0; +https://apify.com)'

SECURITY_HEADERS = {
    'strict-transport-security': 'HSTS',
    'content-security-policy': 'Content-Security-Policy',
    'x-content-type-options': 'X-Content-Type-Options',
    'x-frame-options': 'X-Frame-Options',
    'referrer-policy': 'Referrer-Policy',
    'permissions-policy': 'Permissions-Policy',
}

DOMAIN_RE = re.compile(r'^(?=.{1,253}$)(?!-)([a-z0-9-]{1,63}(?<!-)\.)+[a-z]{2,63}$', re.I)


@dataclass
class AuditOptions:
    check_dns: bool = True
    check_ssl: bool = True
    check_seo: bool = True
    timeout_s: float = 15.0
    allow_private: bool = False  # only for local tests; never exposed in the input schema


def normalize_target(raw: str) -> str:
    """Turn 'example.com', 'https://example.com/path' etc. into a start URL."""
    raw = (raw or '').strip()
    if not raw:
        raise ValueError('empty target')
    if '://' not in raw:
        raw = 'https://' + raw
    parts = urlsplit(raw)
    if parts.scheme not in ('http', 'https') or not parts.hostname:
        raise ValueError(f'invalid URL or domain: {raw!r}')
    host = parts.hostname
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if not DOMAIN_RE.match(host):
            raise ValueError(f'invalid domain name: {host!r}') from None
    path = parts.path or '/'
    return f'{parts.scheme}://{parts.netloc.lower()}{path}' + (f'?{parts.query}' if parts.query else '')


# ---------------------------------------------------------------- HTTP / redirects

async def fetch_with_redirects(client: httpx.AsyncClient, url: str, opts: AuditOptions,
                               max_hops: int = 10) -> dict[str, Any]:
    chain: list[dict[str, Any]] = []
    current = url
    started = time.perf_counter()
    for _ in range(max_hops + 1):
        await assert_public_url(current, allow_private=opts.allow_private)
        resp = await client.get(current, follow_redirects=False)
        chain.append({'url': current, 'status': resp.status_code})
        if resp.is_redirect and 'location' in resp.headers:
            current = urljoin(current, resp.headers['location'])
            continue
        elapsed_ms = round((time.perf_counter() - started) * 1000)
        return {'final_url': current, 'status': resp.status_code, 'chain': chain,
                'response': resp, 'elapsed_ms': elapsed_ms}
    raise RuntimeError(f'Too many redirects (>{max_hops})')


def analyze_security_headers(headers: httpx.Headers | dict[str, str]) -> dict[str, Any]:
    lower = {k.lower(): v for k, v in dict(headers).items()}
    present = {label: lower[h] for h, label in SECURITY_HEADERS.items() if h in lower}
    missing = [label for h, label in SECURITY_HEADERS.items() if h not in lower]
    server = lower.get('server')
    powered = lower.get('x-powered-by')
    return {'present': present, 'missing': missing, 'server': server, 'xPoweredBy': powered}


# ---------------------------------------------------------------- SEO

def analyze_seo(html: str, base_url: str) -> dict[str, Any]:
    soup = BeautifulSoup(html or '', 'lxml')
    title = (soup.title.string or '').strip() if soup.title and soup.title.string else None

    def meta(name: str, attr: str = 'name') -> str | None:
        tag = soup.find('meta', attrs={attr: re.compile(f'^{re.escape(name)}$', re.I)})
        return tag.get('content', '').strip() if tag and tag.get('content') is not None else None

    canonical = soup.find('link', rel=lambda v: v and 'canonical' in (v if isinstance(v, list) else [v]))
    html_tag = soup.find('html')
    imgs = soup.find_all('img')
    return {
        'title': title,
        'titleLength': len(title) if title else 0,
        'metaDescription': meta('description'),
        'metaDescriptionLength': len(meta('description') or ''),
        'canonical': urljoin(base_url, canonical['href']) if canonical and canonical.get('href') else None,
        'robotsMeta': meta('robots'),
        'lang': html_tag.get('lang') if html_tag else None,
        'viewport': meta('viewport'),
        'h1Count': len(soup.find_all('h1')),
        'h1': [h.get_text(' ', strip=True)[:200] for h in soup.find_all('h1')[:3]],
        'imagesTotal': len(imgs),
        'imagesMissingAlt': sum(1 for i in imgs if not (i.get('alt') or '').strip()),
        'openGraph': {k: meta(f'og:{k}', 'property') for k in ('title', 'description', 'image')},
        'favicon': bool(soup.find('link', rel=lambda v: v and 'icon' in ' '.join(v if isinstance(v, list) else [v]).lower())),
    }


async def probe_file(client: httpx.AsyncClient, url: str, opts: AuditOptions) -> dict[str, Any]:
    try:
        await assert_public_url(url, allow_private=opts.allow_private)
        r = await client.get(url, follow_redirects=True)
        ok = r.status_code == 200 and len(r.content) > 0
        return {'url': url, 'status': r.status_code, 'found': ok,
                'sitemaps': re.findall(r'(?im)^\s*sitemap:\s*(\S+)', r.text)[:10] if ok and url.endswith('robots.txt') else None}
    except Exception as e:  # noqa: BLE001
        return {'url': url, 'status': None, 'found': False, 'error': type(e).__name__}


# ---------------------------------------------------------------- SSL

def _cert_time(value: str) -> dt.datetime:
    return dt.datetime.strptime(value, '%b %d %H:%M:%S %Y %Z').replace(tzinfo=dt.timezone.utc)


async def check_ssl(host: str, port: int = 443, timeout_s: float = 10.0) -> dict[str, Any]:
    ctx = ssl.create_default_context()
    result: dict[str, Any] = {'host': host, 'valid': False}
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port, ssl=ctx, server_hostname=host), timeout_s)
        sslobj = writer.get_extra_info('ssl_object')
        cert = sslobj.getpeercert()
        result['tlsVersion'] = sslobj.version()
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:  # noqa: BLE001
            pass
        not_after = _cert_time(cert['notAfter'])
        issuer = dict(x[0] for x in cert.get('issuer', []))
        subject = dict(x[0] for x in cert.get('subject', []))
        sans = [v for k, v in cert.get('subjectAltName', []) if k == 'DNS']
        result.update({
            'valid': True,
            'issuer': issuer.get('organizationName') or issuer.get('commonName'),
            'subject': subject.get('commonName'),
            'validFrom': _cert_time(cert['notBefore']).isoformat(),
            'validTo': not_after.isoformat(),
            'daysUntilExpiry': (not_after - dt.datetime.now(dt.timezone.utc)).days,
            'subjectAltNames': sans[:50],
        })
    except ssl.SSLCertVerificationError as e:
        result['error'] = f'certificate verification failed: {e.verify_message}'
    except (OSError, asyncio.TimeoutError, ssl.SSLError) as e:
        result['error'] = f'{type(e).__name__}: {e}'[:300]
    return result


# ---------------------------------------------------------------- DNS (DNS-over-HTTPS)

DOH_ENDPOINTS = ('https://cloudflare-dns.com/dns-query', 'https://dns.google/resolve')
RTYPES = {'A': 1, 'NS': 2, 'MX': 15, 'TXT': 16, 'AAAA': 28, 'CAA': 257}


async def doh_query(client: httpx.AsyncClient, name: str, rtype: str) -> list[str]:
    """Resolve via public DNS-over-HTTPS (Cloudflare, Google fallback). Returns record data strings."""
    for ep in DOH_ENDPOINTS:
        try:
            r = await client.get(ep, params={'name': name, 'type': rtype},
                                 headers={'accept': 'application/dns-json'})
            if r.status_code != 200:
                continue
            data = r.json()
            want = RTYPES[rtype]
            out = []
            for a in data.get('Answer') or []:
                if a.get('type') != want:
                    continue
                v = str(a.get('data', ''))
                if rtype == 'TXT':  # join quoted chunks: "abc" "def" -> abcdef
                    chunks = re.findall(r'"((?:[^"\\]|\\.)*)"', v)
                    v = ''.join(chunks) if chunks else v
                out.append(v.rstrip('.') if rtype in ('NS', 'A', 'AAAA') else v)
            return sorted(out)
        except (httpx.HTTPError, ValueError):
            continue
    return []


async def check_dns(domain: str, timeout_s: float = 8.0, client: httpx.AsyncClient | None = None) -> dict[str, Any]:
    own = client is None
    client = client or httpx.AsyncClient(timeout=timeout_s)
    try:
        names = [(domain, 'A'), (domain, 'AAAA'), (domain, 'MX'), (domain, 'NS'), (domain, 'TXT'),
                 (domain, 'CAA'), (f'_dmarc.{domain}', 'TXT')]
        a, aaaa, mx, ns, txt, caa, dmarc = await asyncio.gather(*(doh_query(client, n, t) for n, t in names))
    finally:
        if own:
            await client.aclose()
    spf = [t for t in txt if t.lower().startswith('v=spf1')]
    dmarc_rec = [t for t in dmarc if t.lower().startswith('v=dmarc1')]
    return {'A': a, 'AAAA': aaaa, 'MX': mx, 'NS': ns, 'CAA': caa,
            'spf': spf[0] if spf else None, 'dmarc': dmarc_rec[0] if dmarc_rec else None,
            'txtCount': len(txt)}


def registrable_domain(host: str) -> str:
    """Best-effort apex domain (handles common 2-level public suffixes like co.il, co.uk)."""
    parts = host.lower().strip('.').split('.')
    if parts and parts[0] == 'www':
        parts = parts[1:]
    two_level = {'co', 'com', 'org', 'net', 'gov', 'ac', 'edu', 'muni', 'ltd', 'plc'}
    if len(parts) >= 3 and parts[-2] in two_level and len(parts[-1]) == 2:
        return '.'.join(parts[-3:])
    return '.'.join(parts[-2:]) if len(parts) >= 2 else host


# ---------------------------------------------------------------- scoring

def score_and_issues(r: dict[str, Any]) -> tuple[int, list[dict[str, str]]]:
    issues: list[dict[str, str]] = []

    def add(sev: str, code: str, msg: str) -> None:
        issues.append({'severity': sev, 'code': code, 'message': msg})

    http = r.get('http') or {}
    if http.get('error'):
        add('critical', 'UNREACHABLE', f"Site not reachable: {http['error']}")
    else:
        if (http.get('status') or 0) >= 400:
            add('critical', 'HTTP_ERROR', f"Final URL returned HTTP {http.get('status')}")
        if not str(http.get('finalUrl', '')).startswith('https://'):
            add('high', 'NO_HTTPS_REDIRECT', 'Site does not end on HTTPS')
        if len(http.get('redirectChain') or []) > 3:
            add('low', 'LONG_REDIRECT_CHAIN', f"{len(http['redirectChain']) - 1} redirects before final page")
        if (http.get('responseTimeMs') or 0) > 3000:
            add('medium', 'SLOW_RESPONSE', f"Response took {http['responseTimeMs']} ms")
    sec = r.get('securityHeaders') or {}
    for h in sec.get('missing', []):
        add('high' if h == 'HSTS' else 'low', 'MISSING_HEADER', f'Missing security header: {h}')
    if sec.get('xPoweredBy'):
        add('low', 'TECH_DISCLOSURE', f"X-Powered-By header discloses: {sec['xPoweredBy']}")
    ssl_r = r.get('ssl')
    if ssl_r is not None:
        if not ssl_r.get('valid'):
            add('critical', 'SSL_INVALID', ssl_r.get('error') or 'Invalid certificate')
        elif ssl_r.get('daysUntilExpiry', 999) < 14:
            add('high', 'SSL_EXPIRING', f"Certificate expires in {ssl_r['daysUntilExpiry']} days")
        elif ssl_r.get('daysUntilExpiry', 999) < 30:
            add('medium', 'SSL_EXPIRING', f"Certificate expires in {ssl_r['daysUntilExpiry']} days")
    d = r.get('dns')
    if d is not None:
        if d.get('MX') and not d.get('spf'):
            add('medium', 'NO_SPF', 'Domain receives email (MX) but has no SPF record')
        if d.get('MX') and not d.get('dmarc'):
            add('medium', 'NO_DMARC', 'Domain receives email (MX) but has no DMARC record')
        if not d.get('CAA'):
            add('low', 'NO_CAA', 'No CAA record restricting certificate authorities')
    seo = r.get('seo')
    if seo is not None:
        if not seo.get('title'):
            add('high', 'NO_TITLE', 'Page has no <title>')
        elif not 10 <= seo['titleLength'] <= 65:
            add('low', 'TITLE_LENGTH', f"Title length {seo['titleLength']} (recommended 10-65)")
        if not seo.get('metaDescription'):
            add('medium', 'NO_META_DESCRIPTION', 'No meta description')
        elif not 50 <= seo['metaDescriptionLength'] <= 160:
            add('low', 'META_DESCRIPTION_LENGTH', f"Meta description length {seo['metaDescriptionLength']} (recommended 50-160)")
        if seo.get('h1Count', 0) == 0:
            add('medium', 'NO_H1', 'No <h1> heading')
        elif seo['h1Count'] > 1:
            add('low', 'MULTIPLE_H1', f"{seo['h1Count']} <h1> headings")
        if not seo.get('viewport'):
            add('medium', 'NO_VIEWPORT', 'No mobile viewport meta tag')
        if not seo.get('lang'):
            add('low', 'NO_LANG', '<html> has no lang attribute')
        if not seo.get('canonical'):
            add('low', 'NO_CANONICAL', 'No canonical link')
        if seo.get('robotsMeta') and 'noindex' in seo['robotsMeta'].lower():
            add('high', 'NOINDEX', 'Page is set to noindex')
        if seo.get('imagesMissingAlt'):
            add('low', 'IMG_ALT', f"{seo['imagesMissingAlt']} of {seo['imagesTotal']} images missing alt text")
    if r.get('robotsTxt') is not None and not r['robotsTxt'].get('found'):
        add('low', 'NO_ROBOTS_TXT', 'robots.txt not found')
    if r.get('sitemap') is not None and not r['sitemap'].get('found') and not (r.get('robotsTxt') or {}).get('sitemaps'):
        add('low', 'NO_SITEMAP', 'No sitemap.xml found (and none declared in robots.txt)')
    weights = {'critical': 30, 'high': 10, 'medium': 5, 'low': 2}
    score = max(0, 100 - sum(weights[i['severity']] for i in issues))
    return score, issues


# ---------------------------------------------------------------- orchestration

async def audit_target(target: str, opts: AuditOptions, client: httpx.AsyncClient | None = None) -> dict[str, Any]:
    url = normalize_target(target)
    host = urlsplit(url).hostname or ''
    out: dict[str, Any] = {'input': target, 'url': url, 'host': host,
                           'checkedAt': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')}
    own_client = client is None
    client = client or httpx.AsyncClient(timeout=opts.timeout_s, headers={'User-Agent': USER_AGENT},
                                         verify=False)  # cert validity is checked separately in check_ssl
    try:
        tasks: dict[str, Any] = {}
        try:
            res = await fetch_with_redirects(client, url, opts)
            resp: httpx.Response = res['response']
            out['http'] = {'finalUrl': res['final_url'], 'status': res['status'],
                           'redirectChain': res['chain'], 'responseTimeMs': res['elapsed_ms'],
                           'contentType': resp.headers.get('content-type'), 'bytes': len(resp.content)}
            out['securityHeaders'] = analyze_security_headers(resp.headers)
            if opts.check_seo and 'html' in (resp.headers.get('content-type') or ''):
                out['seo'] = analyze_seo(resp.text, res['final_url'])
            final = urlsplit(res['final_url'])
            origin = f'{final.scheme}://{final.netloc}'
            if opts.check_seo:
                tasks['robotsTxt'] = probe_file(client, origin + '/robots.txt', opts)
                tasks['sitemap'] = probe_file(client, origin + '/sitemap.xml', opts)
            ssl_host = final.hostname if final.scheme == 'https' else host
            ssl_host_https = final.scheme == 'https'
        except BlockedAddressError as e:
            out['http'] = {'error': str(e)}
            ssl_host, ssl_host_https = None, False
        except (httpx.HTTPError, RuntimeError, OSError) as e:
            out['http'] = {'error': f'{type(e).__name__}: {e}'[:300]}
            ssl_host, ssl_host_https = host, False
        if opts.check_ssl and ssl_host and (not opts.allow_private or ssl_host_https):
            tasks['ssl'] = check_ssl(ssl_host, timeout_s=opts.timeout_s)
        if opts.check_dns and DOMAIN_RE.match(host):
            tasks['dns'] = check_dns(registrable_domain(host), timeout_s=opts.timeout_s, client=client)
        if tasks:
            results = await asyncio.gather(*tasks.values())
            out.update(dict(zip(tasks.keys(), results)))
        if 'dns' in out:
            out['dns']['domain'] = registrable_domain(host)
        out['score'], out['issues'] = score_and_issues(out)
        out['issueCount'] = len(out['issues'])
        return out
    finally:
        if own_client:
            await client.aclose()
