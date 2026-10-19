"""Offline tests for the time budgets / caps that keep heavy endpoints inside marketplace gateway timeouts."""
import asyncio
import io
import time

import httpx
from PIL import Image, ImageDraw

from engines.links.crawler import CrawlOptions, build_report, crawl
from engines.pdf.extract import ExtractOptions, iter_pages


def _png() -> bytes:
    img = Image.new('L', (600, 120), 255)
    ImageDraw.Draw(img).text((10, 40), 'Hello budget test', fill=0)
    buf = io.BytesIO()
    img.save(buf, 'PNG')
    return buf.getvalue()


def test_ocr_budget_exhausted_returns_partial():
    opts = ExtractOptions(deadline=time.monotonic() - 1)
    pages = list(iter_pages(_png(), opts))
    assert pages[0]['method'] == 'skipped' and 'time budget' in pages[0]['note']
    assert opts.state['timeBudgetExceeded'] is True


def test_image_is_downscaled_before_ocr():
    big = Image.new('L', (4000, 3000), 255)
    buf = io.BytesIO()
    big.save(buf, 'PNG')
    opts = ExtractOptions(max_image_pixels=500_000, deadline=time.monotonic() + 30)
    pages = list(iter_pages(buf.getvalue(), opts))
    assert pages[0]['method'] == 'ocr' and not opts.state.get('timeBudgetExceeded')


def _site(n_external: int):
    links = ''.join(f'<a href="https://ext{i % 7}.example/p{i}">x{i}</a>' for i in range(n_external))
    html = f'<html><body>{links}<a href="/a">a</a></body></html>'

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == 'site.example':
            if request.url.path == '/robots.txt':
                return httpx.Response(404)
            return httpx.Response(200, headers={'content-type': 'text/html'}, text=html)
        return httpx.Response(200)
    return httpx.MockTransport(handler)


def test_broken_links_max_links_cap():
    async def run():
        async with httpx.AsyncClient(transport=_site(300)) as c:
            opts = CrawlOptions(max_pages=2, max_links=50, time_budget_s=10, allow_private=True,
                                per_host_concurrency=4, host_first_batch=10)
            return await crawl('https://site.example/', opts, c)
    res = asyncio.run(run())
    rows, summary = build_report(res)
    assert summary['truncated'] is True and 'max_links' in summary['truncatedReasons']
    assert summary['linksChecked'] <= 52 and summary['linksFound'] > 300


def test_broken_links_time_budget_returns_partial():
    async def slow(request: httpx.Request) -> httpx.Response:
        if request.url.host == 'site.example':
            if request.url.path == '/robots.txt':
                return httpx.Response(404)
            links = ''.join(f'<a href="https://slow{i}.example/">s</a>' for i in range(20))
            return httpx.Response(200, headers={'content-type': 'text/html'}, text=f'<html>{links}</html>')
        await asyncio.sleep(30)
        return httpx.Response(200)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(slow)) as c:
            opts = CrawlOptions(max_pages=1, time_budget_s=2, link_timeout_s=60, allow_private=True)
            t = time.monotonic()
            r = await crawl('https://site.example/', opts, c)
            return r, time.monotonic() - t
    res, took = asyncio.run(run())
    assert took < 4
    assert res['truncated'] and 'time_budget' in res['truncatedReasons']
