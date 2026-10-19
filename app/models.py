"""Request models shared by all access channels (RapidAPI, x402, direct key)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class UrlIn(BaseModel):
    url: str = Field(..., description='Website URL or bare domain, e.g. "example.com"', examples=['example.com'])


class AuditIn(UrlIn):
    check_dns: bool = Field(True, description='Check SPF / DMARC / MX / NS records')
    check_ssl: bool = Field(True, description='Check TLS certificate validity and expiry')
    check_seo: bool = Field(True, description='Check title, meta description, H1, robots.txt, sitemap')


class TechIn(UrlIn):
    min_confidence: int = Field(50, ge=0, le=100, description='Drop detections below this confidence')
    with_dns: bool = Field(True, description='Also use DNS records (email/DNS providers)')


class MarkdownIn(BaseModel):
    url: str = Field(..., examples=['https://en.wikipedia.org/wiki/Markdown'])
    mode: Literal['article', 'full'] = Field('article', description='article = main content only; full = whole page')
    include_links: bool = True
    include_images: bool = False
    include_tables: bool = True
    chunk_size: int = Field(0, ge=0, le=20000, description='If > 0, also return RAG chunks of at most this many characters')
    chunk_overlap: int = Field(200, ge=0, le=2000)


class LinksIn(UrlIn):
    max_pages: int = Field(25, ge=1, le=50, description='Pages of the site to crawl (max 50 per call)')
    check_external: bool = True
    check_resources: bool = Field(False, description='Also check images, scripts and stylesheets')
    include_ok: bool = Field(False, description='Also return working links')
    max_links: int = Field(100, ge=1, le=500, description='Maximum number of links to check (default 100, max 500)')
    time_budget: int = Field(10, ge=5, le=25, description='Time budget in seconds (default 10). When reached, the '
                             'links checked so far are returned with summary.truncated = true')


class PdfIn(BaseModel):
    url: str = Field(..., description='Public URL of a PDF or image (PNG/JPEG/TIFF/WebP)',
                     examples=['https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf'])
    mode: Literal['auto', 'text', 'ocr'] = Field('auto', description='auto = text layer, OCR only scanned pages')
    languages: list[str] = Field(['eng'], description='Tesseract language codes, e.g. ["eng","heb"]')
    output: Literal['markdown', 'text'] = 'markdown'
    max_pages: int = Field(20, ge=1, le=20)
    extract_tables: bool = True
    time_budget: int = Field(10, ge=5, le=25, description='Time budget in seconds (default 10). Pages not processed in '
                             'time are returned as skipped, with timeBudgetExceeded = true and truncated = true')
