"""MCP server (stdio) that gives any AI agent website-audit, tech-detection, page-to-Markdown,
broken-link and PDF/OCR tools, backed by the hosted Web Intelligence API.

Auth (one of):
  RAPIDAPI_KEY      your RapidAPI key (subscribe at the RapidAPI listing; free tier available)
  WEB_INTEL_API_KEY direct API key
Optional:
  WEB_INTEL_BASE_URL  override API host (default: RapidAPI gateway when RAPIDAPI_KEY is set)
"""
from __future__ import annotations

import json
import os
from typing import Any, Literal

import httpx
try:  # mcp >= 2
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server

RAPIDAPI_HOST = os.environ.get('RAPIDAPI_HOST', 'web-intelligence-api.p.rapidapi.com')
mcp = _Server('web-intel')


def _endpoint() -> tuple[str, dict[str, str]]:
    if os.environ.get('RAPIDAPI_KEY'):
        base = os.environ.get('WEB_INTEL_BASE_URL', f'https://{RAPIDAPI_HOST}')
        return base, {'X-RapidAPI-Key': os.environ['RAPIDAPI_KEY'], 'X-RapidAPI-Host': RAPIDAPI_HOST}
    if os.environ.get('WEB_INTEL_API_KEY'):
        return os.environ.get('WEB_INTEL_BASE_URL', 'http://localhost:8000'), {'X-API-Key': os.environ['WEB_INTEL_API_KEY']}
    raise RuntimeError('Set RAPIDAPI_KEY (get a free key on the RapidAPI listing) or WEB_INTEL_API_KEY.')


async def _call(path: str, body: dict[str, Any]) -> str:
    base, headers = _endpoint()
    async with httpx.AsyncClient(timeout=150) as client:
        r = await client.post(f'{base.rstrip("/")}/v1{path}', json=body, headers=headers)
    if r.status_code >= 400:
        return json.dumps({'error': r.status_code, 'detail': r.text[:500]})
    return r.text


@mcp.tool()
async def website_health_audit(url: str) -> str:
    """Audit a website: HTTP status & redirects, SSL certificate expiry, DNS (SPF/DMARC/MX), security headers,
    SEO basics (title, meta description, H1, robots.txt, sitemap) and a 0-100 health score with issues."""
    return await _call('/health-audit', {'url': url})


@mcp.tool()
async def detect_tech_stack(url: str, min_confidence: int = 50) -> str:
    """Detect technologies a website uses (CMS, e-commerce, frameworks, analytics, CDN, hosting, email provider)."""
    return await _call('/tech-detect', {'url': url, 'min_confidence': min_confidence})


@mcp.tool()
async def page_to_markdown(url: str, mode: Literal['article', 'full'] = 'article', chunk_size: int = 0) -> str:
    """Fetch a web page and return clean Markdown (main content), title, author, date; optional RAG chunks."""
    return await _call('/markdown', {'url': url, 'mode': mode, 'chunk_size': chunk_size})


@mcp.tool()
async def find_broken_links(url: str, max_pages: int = 25) -> str:
    """Crawl up to 50 pages of a website and list broken links with the page each was found on."""
    return await _call('/broken-links', {'url': url, 'max_pages': max_pages})


@mcp.tool()
async def extract_pdf_text(url: str, languages: list[str] | None = None, mode: Literal['auto', 'text', 'ocr'] = 'auto') -> str:
    """Extract text and tables from a PDF/image URL; OCR for scanned pages (e.g. languages=["eng","heb"])."""
    return await _call('/pdf-extract', {'url': url, 'languages': languages or ['eng'], 'mode': mode})


def main() -> None:
    mcp.run()


if __name__ == '__main__':
    main()
