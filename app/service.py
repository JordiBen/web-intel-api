"""Thin adapters from API requests to the vendored Actor engines (engines/*). No Apify dependency."""
from __future__ import annotations

import asyncio
import datetime as dt
import os
from functools import lru_cache
from typing import Any

import httpx

from engines.health.audit import USER_AGENT as HEALTH_UA, AuditOptions, audit_target
from engines.links.crawler import USER_AGENT as LINKS_UA, CrawlOptions, build_report, crawl
from engines.markdown.convert import USER_AGENT as MD_UA, RobotsCache, chunk_markdown, fetch_html, html_to_markdown, normalize_url
from engines.pdf.extract import DocumentError, ExtractOptions, available_languages, download, iter_pages, to_markdown
from engines.tech.detector import Fingerprints, detect
from engines.tech.fetch import USER_AGENT as TECH_UA, collect

from .models import AuditIn, LinksIn, MarkdownIn, PdfIn, TechIn

ALLOW_PRIVATE = os.environ.get('ALLOW_PRIVATE_NETWORK_FOR_LOCAL_DEV') == '1'  # tests only
# Bounded concurrency keeps a small free-tier instance (512 MB) alive under bursts.
HEAVY = asyncio.Semaphore(int(os.environ.get('MAX_HEAVY_JOBS', '2')))   # OCR, crawls
LIGHT = asyncio.Semaphore(int(os.environ.get('MAX_LIGHT_JOBS', '8')))


class UserInputError(Exception):
    """Bad input or target that the caller can fix -> HTTP 422."""


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


@lru_cache(maxsize=1)
def fingerprints() -> Fingerprints:
    return Fingerprints()


async def health_audit(req: AuditIn) -> dict[str, Any]:
    opts = AuditOptions(check_dns=req.check_dns, check_ssl=req.check_ssl, check_seo=req.check_seo,
                        timeout_s=15, allow_private=ALLOW_PRIVATE)
    async with LIGHT:
        try:
            return await audit_target(req.url, opts)
        except ValueError as e:
            raise UserInputError(str(e)) from e


async def tech_detect(req: TechIn) -> dict[str, Any]:
    fp = fingerprints()
    async with LIGHT, httpx.AsyncClient(timeout=20, headers={'User-Agent': TECH_UA}, verify=False) as client:
        try:
            sig, meta = await collect(client, req.url, timeout=20, with_dns=req.with_dns, allow_private=ALLOW_PRIVATE)
        except ValueError as e:
            raise UserInputError(str(e)) from e
        techs = await asyncio.to_thread(detect, fp, sig)
    techs = [t for t in techs if t['confidence'] >= req.min_confidence]
    return {'input': req.url, 'checkedAt': _now(), **meta, 'technologyCount': len(techs),
            'categories': sorted({c for t in techs for c in t['categories']}), 'technologies': techs}


async def page_markdown(req: MarkdownIn) -> dict[str, Any]:
    try:
        url = normalize_url(req.url)
    except ValueError as e:
        raise UserInputError(str(e)) from e
    async with LIGHT, httpx.AsyncClient(timeout=30, headers={'User-Agent': MD_UA}) as client:
        if not await RobotsCache(client).allowed(url):
            raise UserInputError('disallowed by the site robots.txt')
        try:
            html, final, status, ctype = await fetch_html(client, url, allow_private=ALLOW_PRIVATE)
        except ValueError as e:
            raise UserInputError(str(e)) from e
    if status >= 400:
        raise UserInputError(f'target returned HTTP {status}')
    if 'html' not in ctype and not html.lstrip().startswith('<'):
        raise UserInputError(f'not an HTML page ({ctype or "unknown type"})')
    res = await asyncio.to_thread(html_to_markdown, html, final, req.mode, req.include_links,
                                  req.include_images, req.include_tables)
    out = {'url': url, 'finalUrl': final, 'statusCode': status, 'crawledAt': _now(), **res}
    if req.chunk_size:
        out['chunks'] = chunk_markdown(res['markdown'], req.chunk_size, req.chunk_overlap)
    return out


async def broken_links(req: LinksIn) -> dict[str, Any]:
    opts = CrawlOptions(max_pages=req.max_pages, max_depth=5, check_external=req.check_external,
                        check_resources=req.check_resources, respect_robots=True, concurrency=5,
                        timeout_s=15, allow_private=ALLOW_PRIVATE)
    async with HEAVY, httpx.AsyncClient(timeout=15, headers={'User-Agent': LINKS_UA},
                                        limits=httpx.Limits(max_connections=20)) as client:
        try:
            start = req.url.strip()
            if '://' not in start:  # the model documents bare domains ("example.com") as valid input
                start = 'https://' + start
            result = await asyncio.wait_for(crawl(start, opts, client), timeout=110)
        except ValueError as e:
            raise UserInputError(str(e)) from e
    rows, summary = build_report(result, include_ok=req.include_ok)
    return {'startUrl': req.url, 'checkedAt': _now(), 'summary': summary, 'links': rows}


async def pdf_extract(req: PdfIn) -> dict[str, Any]:
    missing = set(req.languages) - available_languages()
    if req.mode != 'text' and missing:
        raise UserInputError(f'OCR language not installed: {sorted(missing)}; available: {sorted(available_languages())}')
    opts = ExtractOptions(languages=tuple(req.languages), mode=req.mode, extract_tables=req.extract_tables,
                          max_pages=req.max_pages, dpi=200, max_bytes=25 * 1024 * 1024, allow_private=ALLOW_PRIVATE)
    async with HEAVY, httpx.AsyncClient(timeout=60, headers={'User-Agent': 'Mozilla/5.0 (compatible; PdfOcrExtractor/1.0)'}) as client:
        try:
            data = await download(client, req.url, opts)
            pages = await asyncio.to_thread(lambda: list(iter_pages(data, opts)))
        except (DocumentError, ValueError) as e:
            raise UserInputError(str(e)) from e
    content = to_markdown(pages) if req.output == 'markdown' else '\n\n'.join(p['text'] for p in pages if p['text'])
    return {'url': req.url, 'bytes': len(data), 'pageCount': len(pages),
            'ocrPages': sum(p['method'] == 'ocr' for p in pages),
            'textLayerPages': sum(p['method'] == 'text' for p in pages),
            'tableCount': sum(len(p['tables']) for p in pages), 'format': req.output,
            'truncated': len(pages) >= req.max_pages, 'content': content, 'pages': pages}
