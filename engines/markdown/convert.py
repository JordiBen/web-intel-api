"""Fetch a public web page (robots.txt-aware) and turn it into clean Markdown + metadata + RAG chunks."""
from __future__ import annotations

import asyncio
import re
import urllib.robotparser
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx
import trafilatura
from bs4 import BeautifulSoup
from markdownify import markdownify

from .netguard import assert_public_url

USER_AGENT = 'Mozilla/5.0 (compatible; PageToMarkdown/1.0; +https://apify.com)'
ROBOTS_AGENT = 'PageToMarkdown'
MAX_BYTES = 8 * 1024 * 1024


def normalize_url(raw: str) -> str:
    raw = (raw or '').strip()
    if not raw:
        raise ValueError('empty URL')
    if '://' not in raw:
        raw = 'https://' + raw
    p = urlsplit(raw)
    if p.scheme not in ('http', 'https') or not p.hostname or not re.match(r'^[a-z0-9.-]+$', p.hostname, re.I):
        raise ValueError(f'invalid URL: {raw!r}')
    return p._replace(fragment='', path=p.path or '/').geturl()


class RobotsCache:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client
        self.cache: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self.locks: dict[str, asyncio.Lock] = {}

    async def allowed(self, url: str) -> bool:
        p = urlsplit(url)
        origin = f'{p.scheme}://{p.netloc}'
        lock = self.locks.setdefault(origin, asyncio.Lock())
        async with lock:
            if origin not in self.cache:
                rp = None
                try:
                    r = await self.client.get(origin + '/robots.txt', follow_redirects=True)
                    if r.status_code < 400:
                        rp = urllib.robotparser.RobotFileParser()
                        rp.parse(r.text.splitlines())
                except httpx.HTTPError:
                    rp = None
                self.cache[origin] = rp
        rp = self.cache[origin]
        return rp is None or rp.can_fetch(ROBOTS_AGENT, url)


async def fetch_html(client: httpx.AsyncClient, url: str, *, allow_private: bool = False) -> tuple[str, str, int, str]:
    current = url
    for _ in range(10):
        await assert_public_url(current, allow_private=allow_private)
        async with client.stream('GET', current, follow_redirects=False) as r:
            if r.is_redirect and 'location' in r.headers:
                current = urljoin(current, r.headers['location'])
                continue
            ctype = r.headers.get('content-type', '')
            buf = bytearray()
            async for chunk in r.aiter_bytes():
                buf.extend(chunk)
                if len(buf) > MAX_BYTES:
                    raise ValueError('page larger than 8 MB')
            enc = r.encoding or 'utf-8'
            text = bytes(buf).decode(enc, errors='replace')
            return text, current, r.status_code, ctype
    raise ValueError('too many redirects')


def _clean_md(md: str) -> str:
    md = re.sub(r'\n{3,}', '\n\n', md or '')
    return md.strip()


def html_to_markdown(html: str, url: str, mode: str = 'article', include_links: bool = True,
                     include_images: bool = False, include_tables: bool = True) -> dict[str, Any]:
    meta = trafilatura.extract_metadata(html, default_url=url)
    soup = BeautifulSoup(html, 'lxml')
    title = (meta.title if meta and meta.title else (soup.title.get_text(strip=True) if soup.title else None))
    content = None
    used = mode
    if mode == 'article':
        content = trafilatura.extract(html, url=url, output_format='markdown', include_links=include_links,
                                      include_images=include_images, include_tables=include_tables,
                                      include_comments=False, favor_recall=True, with_metadata=False)
        if not content or len(content) < 200:
            used = 'full'  # extraction found no clear main content (e.g. landing pages): fall back
    if used == 'full':
        for t in soup(['script', 'style', 'noscript', 'svg', 'iframe', 'template', 'form']):
            t.decompose()
        for t in soup.select('nav, footer, header, aside, [role=navigation], [aria-hidden=true]'):
            t.decompose()
        body = soup.body or soup
        strip = ['a'] if not include_links else []
        if not include_images:
            strip.append('img')
        content = markdownify(str(body), heading_style='ATX', strip=strip or None, bullets='-')
    content = _clean_md(content or '')
    if title and not re.search(r'^# ', content[:500], re.M):
        content = f'# {title}\n\n{content}'
    words = len(re.findall(r'\w+', content))
    return {
        'title': title,
        'description': meta.description if meta else None,
        'author': meta.author if meta else None,
        'publishedDate': meta.date if meta else None,
        'siteName': meta.sitename if meta else None,
        'language': (soup.html.get('lang') if soup.html else None),
        'extractionMode': used,
        'markdown': content,
        'wordCount': words,
        'estimatedTokens': round(len(content) / 4),
    }


def chunk_markdown(md: str, max_chars: int = 2000, overlap: int = 200) -> list[str]:
    """Split on headings/paragraphs, packing into chunks <= max_chars, with character overlap."""
    if max_chars <= 0 or len(md) <= max_chars:
        return [md] if md else []
    blocks = re.split(r'\n(?=#{1,6} )|\n\n', md)
    chunks, cur = [], ''
    for b in blocks:
        b = b.strip()
        if not b:
            continue
        while len(b) > max_chars:  # very long paragraph: hard split
            head, b = b[:max_chars], b[max_chars - overlap:]
            if cur:
                chunks.append(cur)
                cur = ''
            chunks.append(head)
        if len(cur) + len(b) + 2 > max_chars and cur:
            chunks.append(cur)
            cur = (cur[-overlap:] + '\n\n' if overlap else '') + b
        else:
            cur = f'{cur}\n\n{b}' if cur else b
    if cur:
        chunks.append(cur)
    return chunks
