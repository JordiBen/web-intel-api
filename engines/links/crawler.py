"""Same-site crawler that finds broken links, images, scripts and stylesheets. No Apify dependency."""
from __future__ import annotations

import asyncio
import time
import urllib.robotparser
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable
from urllib.parse import urldefrag, urljoin, urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup

from .netguard import BlockedAddressError, assert_public_url

USER_AGENT = 'Mozilla/5.0 (compatible; BrokenLinkChecker/1.0; +https://apify.com)'
ROBOTS_AGENT = 'BrokenLinkChecker'
SKIP_SCHEMES = ('mailto:', 'tel:', 'javascript:', 'data:', 'sms:', 'ftp:', 'blob:', 'about:')

# tag -> (attribute, resource type)
RESOURCE_TAGS = {
    'a': ('href', 'link'), 'img': ('src', 'image'), 'script': ('src', 'script'),
    'iframe': ('src', 'iframe'), 'source': ('src', 'media'), 'video': ('src', 'media'),
    'audio': ('src', 'media'),
}


@dataclass
class CrawlOptions:
    max_pages: int = 200
    max_depth: int = 10
    check_external: bool = True
    check_resources: bool = True  # images, scripts, stylesheets, iframes
    respect_robots: bool = True
    concurrency: int = 5
    timeout_s: float = 15.0
    include_subdomains: bool = False
    allow_private: bool = False  # tests only


@dataclass
class LinkInfo:
    url: str
    resource_type: str
    internal: bool
    found_on: list[str] = field(default_factory=list)
    anchor_texts: list[str] = field(default_factory=list)


def normalize_url(href: str, base: str) -> str | None:
    href = (href or '').strip()
    if not href or href.startswith('#') or href.lower().startswith(SKIP_SCHEMES):
        return None
    absolute, _ = urldefrag(urljoin(base, href))
    p = urlsplit(absolute)
    if p.scheme not in ('http', 'https') or not p.hostname:
        return None
    netloc = p.hostname.lower() + (f':{p.port}' if p.port and p.port not in (80, 443) else '')
    return urlunsplit((p.scheme, netloc, p.path or '/', p.query, ''))


def site_key(host: str) -> str:
    host = (host or '').lower()
    return host[4:] if host.startswith('www.') else host


def is_internal(url: str, root_host: str, include_subdomains: bool) -> bool:
    h = site_key(urlsplit(url).hostname or '')
    root = site_key(root_host)
    return h == root or (include_subdomains and h.endswith('.' + root))


def extract_links(html: str, page_url: str, check_resources: bool) -> list[tuple[str, str, str]]:
    """Return (url, resource_type, anchor_text) tuples found in the page."""
    soup = BeautifulSoup(html or '', 'lxml')
    base_tag = soup.find('base', href=True)
    base = urljoin(page_url, base_tag['href']) if base_tag else page_url
    out = []
    for tag, (attr, rtype) in RESOURCE_TAGS.items():
        if rtype != 'link' and not check_resources:
            continue
        for el in soup.find_all(tag):
            u = normalize_url(el.get(attr), base)
            if u:
                text = el.get_text(' ', strip=True)[:120] if tag == 'a' else (el.get('alt') or '')[:120]
                out.append((u, rtype, text))
    if check_resources:
        for el in soup.find_all('link', href=True):
            rel = ' '.join(el.get('rel') or []).lower()
            if 'stylesheet' in rel or 'icon' in rel:
                u = normalize_url(el['href'], base)
                if u:
                    out.append((u, 'stylesheet' if 'stylesheet' in rel else 'icon', ''))
    return out


def verdict(status: int | None, error: str | None) -> str:
    if error:
        return 'broken'
    if status is None:
        return 'broken'
    if status in (401, 403, 429, 999):
        return 'blocked'  # server refused the checker; may work in a browser
    if status >= 400:
        return 'broken'
    return 'ok'


class LinkChecker:
    def __init__(self, client: httpx.AsyncClient, opts: CrawlOptions):
        self.client, self.opts = client, opts
        self.cache: dict[str, dict[str, Any]] = {}
        self.locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        # be polite: at most 2 parallel checks per host (avoids 429s from e.g. github.com)
        self.host_sems: dict[str, asyncio.Semaphore] = defaultdict(lambda: asyncio.Semaphore(2))
        self.host_429: dict[str, int] = defaultdict(int)

    async def check(self, url: str) -> dict[str, Any]:
        async with self.locks[url]:
            if url in self.cache:
                return self.cache[url]
            host = urlsplit(url).hostname or ''
            async with self.host_sems[host]:
                if self.host_429[host] >= 3:
                    # host keeps rate-limiting us: stop hammering it, report as blocked (not broken)
                    res = {'status': 429, 'error': 'host rate-limited the checker; not re-tested',
                           'finalUrl': None, 'redirects': 0, 'verdict': 'blocked', 'responseTimeMs': None}
                else:
                    res = await self._check(url)
                    if res['status'] == 429:
                        self.host_429[host] += 1
                        ra = res.get('retryAfter') or 2
                        if ra <= 5 and self.host_429[host] < 3:  # one quick polite retry
                            await asyncio.sleep(ra)
                            res = await self._check(url)
            res.pop('retryAfter', None)
            self.cache[url] = res
            return res

    async def _check(self, url: str) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            await assert_public_url(url, allow_private=self.opts.allow_private)
            r = await self.client.head(url, follow_redirects=True)
            if r.status_code >= 400:  # many servers mishandle HEAD; confirm with GET
                async with self.client.stream('GET', url, follow_redirects=True) as r2:
                    r = r2
            status, err = r.status_code, None
            final = str(r.url)
            redirects = len(r.history)
            retry_after = r.headers.get('retry-after') if status == 429 else None
        except BlockedAddressError as e:
            status, err, final, redirects, retry_after = None, f'blocked: {e}', None, 0, None
        except httpx.TimeoutException:
            status, err, final, redirects, retry_after = None, 'timeout', None, 0, None
        except httpx.HTTPError as e:
            status, err, final, redirects, retry_after = None, f'{type(e).__name__}: {e}'[:200], None, 0, None
        try:
            retry_after = float(retry_after) if retry_after else None
        except ValueError:
            retry_after = None
        return {'retryAfter': retry_after, 'status': status, 'error': err, 'finalUrl': final if final != url else None,
                'redirects': redirects, 'verdict': verdict(status, err),
                'responseTimeMs': round((time.perf_counter() - started) * 1000)}


async def load_robots(client: httpx.AsyncClient, origin: str) -> urllib.robotparser.RobotFileParser | None:
    rp = urllib.robotparser.RobotFileParser()
    try:
        r = await client.get(origin + '/robots.txt', follow_redirects=True)
        if r.status_code >= 400:
            return None
        rp.parse(r.text.splitlines())
        return rp
    except httpx.HTTPError:
        return None


async def crawl(start_url: str, opts: CrawlOptions, client: httpx.AsyncClient,
                on_page: Callable[[str], Awaitable[bool]] | None = None) -> dict[str, Any]:
    """Crawl the site. on_page(url) is awaited for every HTML page parsed; returning False stops the crawl.

    Returns {'pages': [...], 'links': {url: LinkInfo}, 'results': {url: check-result}, 'stoppedEarly': bool}
    """
    start = normalize_url(start_url, start_url)
    if not start:
        raise ValueError(f'Invalid start URL: {start_url!r}')
    await assert_public_url(start, allow_private=opts.allow_private)
    root_host = urlsplit(start).hostname or ''
    origin = '{0.scheme}://{0.netloc}'.format(urlsplit(start))
    robots = await load_robots(client, origin) if opts.respect_robots else None

    checker = LinkChecker(client, opts)
    links: dict[str, LinkInfo] = {}
    pages: list[dict[str, Any]] = []
    parsed: set[str] = set()
    crawled = [0]  # HTML pages actually parsed (robots-skipped pages don't count toward max_pages)
    queued = {start}
    queue: asyncio.Queue[tuple[str, int, str | None]] = asyncio.Queue()
    queue.put_nowait((start, 0, None))
    stop = asyncio.Event()
    sem = asyncio.Semaphore(opts.concurrency)
    pending_checks: set[asyncio.Task] = set()

    def allowed(url: str) -> bool:
        return robots is None or robots.can_fetch(ROBOTS_AGENT, url)

    async def fetch_page(url: str, depth: int) -> None:
        async with sem:
            if stop.is_set() or crawled[0] >= opts.max_pages:
                return
            if not allowed(url):
                pages.append({'url': url, 'status': None, 'skipped': 'robots.txt'})
                checker.cache[url] = {'status': None, 'error': None, 'finalUrl': None, 'redirects': 0,
                                      'verdict': 'skipped', 'responseTimeMs': None}
                return
            try:
                await assert_public_url(url, allow_private=opts.allow_private)
                r = await client.get(url, follow_redirects=True)
            except (httpx.HTTPError, BlockedAddressError) as e:
                checker.cache.setdefault(url, {'status': None, 'error': f'{type(e).__name__}: {e}'[:200],
                                               'finalUrl': None, 'redirects': 0, 'verdict': 'broken',
                                               'responseTimeMs': None})
                return
            checker.cache.setdefault(url, {'status': r.status_code, 'error': None,
                                           'finalUrl': str(r.url) if str(r.url) != url else None,
                                           'redirects': len(r.history), 'verdict': verdict(r.status_code, None),
                                           'responseTimeMs': None})
            ctype = r.headers.get('content-type', '')
            final_internal = is_internal(str(r.url), root_host, opts.include_subdomains)
            if r.status_code >= 400 or 'html' not in ctype or not final_internal:
                return
            final_url = normalize_url(str(r.url), str(r.url)) or url
            if final_url != url:
                if final_url in parsed:
                    return  # redirect to a page we already parse; don't double-count it
                queued.add(final_url)
            if url in parsed or crawled[0] >= opts.max_pages:
                return
            parsed.update({url, final_url})
            crawled[0] += 1
            url = final_url
            pages.append({'url': url, 'status': r.status_code, 'depth': depth})
            if on_page is not None and not await on_page(url):
                stop.set()
                return
            for link_url, rtype, text in extract_links(r.text, str(r.url), opts.check_resources):
                internal = is_internal(link_url, root_host, opts.include_subdomains)
                info = links.get(link_url)
                if info is None:
                    info = links[link_url] = LinkInfo(link_url, rtype, internal)
                if len(info.found_on) < 20 and url not in info.found_on:
                    info.found_on.append(url)
                if text and len(info.anchor_texts) < 5 and text not in info.anchor_texts:
                    info.anchor_texts.append(text)
                if internal and rtype == 'link' and depth + 1 <= opts.max_depth and link_url not in queued:
                    queued.add(link_url)
                    queue.put_nowait((link_url, depth + 1, url))
                elif (not internal and opts.check_external) or (internal and rtype != 'link'):
                    if link_url not in checker.cache:
                        t = asyncio.create_task(_bounded_check(link_url))
                        pending_checks.add(t)
                        t.add_done_callback(pending_checks.discard)

    check_sem = asyncio.Semaphore(max(2, opts.concurrency * 2))

    async def _bounded_check(u: str) -> None:
        async with check_sem:
            await checker.check(u)

    in_flight: set[asyncio.Task] = set()
    while not stop.is_set():
        while not queue.empty() and crawled[0] + len(in_flight) < opts.max_pages + opts.concurrency:
            url, depth, _ = queue.get_nowait()
            t = asyncio.create_task(fetch_page(url, depth))
            in_flight.add(t)
            t.add_done_callback(in_flight.discard)
        if not in_flight:
            if queue.empty() or crawled[0] >= opts.max_pages:
                break
            continue
        await asyncio.wait(in_flight, return_when=asyncio.FIRST_COMPLETED)
        if crawled[0] >= opts.max_pages:
            break
    if in_flight:
        await asyncio.gather(*in_flight, return_exceptions=True)
    # internal links that were queued but never fetched (page limit) still get a status check
    for u, info in links.items():
        if info.internal and not allowed(u):
            continue  # never touch URLs the site disallows for crawlers
        if u not in checker.cache and (info.internal or opts.check_external):
            t = asyncio.create_task(_bounded_check(u))
            pending_checks.add(t)
    if pending_checks:
        await asyncio.gather(*list(pending_checks), return_exceptions=True)
    return {'pages': pages, 'links': links, 'results': checker.cache, 'stoppedEarly': stop.is_set(),
            'robotsTxtUsed': robots is not None}


def build_report(crawl_result: dict[str, Any], include_ok: bool = False) -> tuple[list[dict], dict]:
    rows = []
    counts = defaultdict(int)
    for url, info in crawl_result['links'].items():
        res = crawl_result['results'].get(url)
        if res is None:
            continue
        counts[res['verdict']] += 1
        if res['verdict'] in ('ok', 'skipped') and not include_ok:
            continue
        rows.append({'url': url, 'verdict': res['verdict'], 'status': res['status'], 'error': res['error'],
                     'finalUrl': res['finalUrl'], 'redirects': res['redirects'],
                     'resourceType': info.resource_type, 'internal': info.internal,
                     'foundOn': info.found_on, 'anchorTexts': info.anchor_texts})
    order = {'broken': 0, 'blocked': 1, 'ok': 2, 'skipped': 3}
    rows.sort(key=lambda r: (order[r['verdict']], not r['internal'], r['url']))
    summary = {'pagesCrawled': sum(1 for p in crawl_result['pages'] if p.get('status')),
               'pagesSkippedByRobots': sum(1 for p in crawl_result['pages'] if p.get('skipped')),
               'linksChecked': sum(v for k, v in counts.items() if k != 'skipped'), 'broken': counts['broken'], 'blocked': counts['blocked'],
               'ok': counts['ok'], 'stoppedEarly': crawl_result['stoppedEarly'],
               'robotsTxtUsed': crawl_result['robotsTxtUsed']}
    return rows, summary
