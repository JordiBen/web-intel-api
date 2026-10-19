"""Thin adapters from API requests to the vendored Actor engines (engines/*). No Apify dependency."""
from __future__ import annotations

import asyncio
import datetime as dt
import os
import time
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


def _budget_left(t0: float, budget: float, floor: float = 4.0) -> float:
    """Budget left after waiting for a heavy-job slot (never below `floor`, so a queued call still does some work)."""
    return max(floor, budget - (time.monotonic() - t0))


async def broken_links(req: LinksIn) -> dict[str, Any]:
    t0 = time.monotonic()
    async with HEAVY:
        budget = _budget_left(t0, req.time_budget)
        opts = CrawlOptions(max_pages=req.max_pages, max_depth=5, check_external=req.check_external,
                            check_resources=req.check_resources, respect_robots=True, concurrency=5,
                            timeout_s=8, link_timeout_s=5, check_concurrency=20, max_links=req.max_links,
                            per_host_concurrency=4, host_first_batch=10,
                            time_budget_s=budget, allow_private=ALLOW_PRIVATE)
        async with httpx.AsyncClient(timeout=httpx.Timeout(8, connect=4), headers={'User-Agent': LINKS_UA},
                                     limits=httpx.Limits(max_connections=30)) as client:
            try:
                start = req.url.strip()
                if '://' not in start:  # the model documents bare domains ("example.com") as valid input
                    start = 'https://' + start
                # safety net only: crawl() itself stops at the budget and returns partial results
                result = await asyncio.wait_for(crawl(start, opts, client), timeout=budget + 8)
            except ValueError as e:
                raise UserInputError(str(e)) from e
    rows, summary = build_report(result, include_ok=req.include_ok)
    return {'startUrl': req.url, 'checkedAt': _now(), 'summary': summary, 'links': rows,
            'truncated': summary['truncated']}


async def pdf_extract(req: PdfIn) -> dict[str, Any]:
    missing = set(req.languages) - available_languages()
    if req.mode != 'text' and missing:
        raise UserInputError(f'OCR language not installed: {sorted(missing)}; available: {sorted(available_languages())}')
    t0 = time.monotonic()
    async with HEAVY:
        budget = _budget_left(t0, req.time_budget)
        slot = time.monotonic()
        opts = ExtractOptions(languages=tuple(req.languages), mode=req.mode, extract_tables=req.extract_tables,
                              max_pages=req.max_pages, dpi=150, max_bytes=25 * 1024 * 1024, allow_private=ALLOW_PRIVATE,
                              max_image_pixels=int(os.environ.get('OCR_MAX_PIXELS', '3000000')))
        dl_timeout = min(10.0, budget * 0.5)
        async with httpx.AsyncClient(timeout=httpx.Timeout(dl_timeout, connect=5),
                                     headers={'User-Agent': 'Mozilla/5.0 (compatible; PdfOcrExtractor/1.0)'}) as client:
            try:
                data = await asyncio.wait_for(download(client, req.url, opts), timeout=dl_timeout + 2)
            except (asyncio.TimeoutError, httpx.TimeoutException) as e:
                raise UserInputError(f'download took longer than {dl_timeout:.0f} s') from e
            except httpx.HTTPError as e:
                raise UserInputError(f'download failed: {type(e).__name__}') from e
            except (DocumentError, ValueError) as e:
                raise UserInputError(str(e)) from e
        opts.deadline = max(slot + budget - 0.5, time.monotonic() + 1.0)  # budget covers download + extraction
        try:
            pages = await asyncio.to_thread(lambda: list(iter_pages(data, opts)))
        except (DocumentError, ValueError) as e:
            raise UserInputError(str(e)) from e
    over = bool(opts.state.get('timeBudgetExceeded'))
    content = to_markdown(pages) if req.output == 'markdown' else '\n\n'.join(p['text'] for p in pages if p['text'])
    return {'url': req.url, 'bytes': len(data), 'pageCount': len(pages),
            'ocrPages': sum(p['method'] == 'ocr' for p in pages),
            'textLayerPages': sum(p['method'] == 'text' for p in pages),
            'tableCount': sum(len(p['tables']) for p in pages), 'format': req.output,
            'truncated': len(pages) >= req.max_pages or over, 'timeBudgetExceeded': over,
            'elapsedMs': round((time.monotonic() - t0) * 1000), 'content': content, 'pages': pages}
