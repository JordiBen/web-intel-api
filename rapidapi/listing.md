# RapidAPI listing: Web Intelligence API

## General tab
- **API name:** Web Intelligence API
- **Short description (≤ 100 chars):** Website audit, tech-stack detection, page-to-Markdown, broken links & PDF/OCR in one API
- **Category:** Data (alternatives: Tools, Text Analysis)
- **Website:** https://github.com/JordiBen/web-intel-api
- **Terms of use:** https://github.com/JordiBen/web-intel-api/blob/main/LICENSE (code is GPL-3.0; see "Terms" below for a one-paragraph service ToS to paste)
- **Logo:** optional; skip for now

## Long description (paste into "Long Description", Markdown allowed)
**Five website and document tools behind one key, built for agencies, SEO tools, lead-gen enrichment and AI agents.**

| Endpoint | What you get |
|---|---|
| `POST /v1/health-audit` | HTTP status, redirect chain, response time, SSL validity and days to expiry, SPF/DMARC/MX/NS, security headers, SEO basics (title, meta description, H1, canonical, robots.txt, sitemap) and a 0–100 score with prioritized issues |
| `POST /v1/tech-detect` | CMS, e-commerce, frameworks, analytics, tag managers, CDN, hosting, email and DNS providers, with versions and confidence. Uses 3,000+ open fingerprints (HTTP Archive / Wappalyzer data) |
| `POST /v1/markdown` | Any article or page as clean Markdown (main-content extraction), with title, author, date and language, plus optional RAG chunks with overlap |
| `POST /v1/broken-links` | Crawls up to 50 pages and lists every broken link (404, 5xx, DNS errors, timeouts) with the page and anchor text where it was found. Respects robots.txt |
| `POST /v1/pdf-extract` | Text and tables from PDFs and images, with OCR on scanned pages in English, Hebrew, Arabic, German, French and Spanish. Fixes RTL text. Up to 20 pages per call |

- Plain JSON in, JSON out. Each endpoint takes `url` plus optional switches; see each endpoint's example.
- Private and internal addresses are blocked for safety.
- Open source: https://github.com/JordiBen/web-intel-api
- MCP server for Claude, Cursor and other agents: see the repo's `mcp_server/` folder.

**Typical uses:** auditing a prospect's website before a sales call, enriching lead lists with tech stack, feeding web pages to LLMs, monitoring sites for broken links and expiring certificates, and getting text out of scanned PDFs.

## Terms (paste into Terms of Use if a text field is offered)
The service is provided "as is", without warranty. Don't use it to scan systems you're not authorized to test, or in breach of the target site's terms. Requests are processed in memory and not stored, except for the hosting provider's standard short-lived request logs. Fair use: a burst limit applies per plan.

## Base URL and gateway
- **Base URL:** `https://web-intel-api.onrender.com`
- **Import spec:** upload `rapidapi/openapi.json` under Definitions → Import (OpenAPI 3).
- **Gateway → Firewall settings → Proxy secret:** copy the value RapidAPI shows, and I'll set it as the Render env var `RAPIDAPI_PROXY_SECRET` (it replaces the placeholder). Any call that doesn't come through RapidAPI is rejected with 401.
- **Request timeout:** set the maximum offered (≥ 120 s). Broken-links and OCR calls can take 30–100 s on the free host.

## Plans (Monetize tab)
| Plan | Price/mo | Quota (requests/mo) | Overage | Rate limit |
|---|---|---|---|---|
| Basic | $0 | 50 | hard limit (no overage) | 1 req/s |
| Pro | $9.99 | 2,000 | $0.005/req | 3 req/s |
| Ultra | $29.99 | 10,000 | $0.004/req | 5 req/s |
| Mega | $99 | 50,000 | $0.003/req | 10 req/s |

- **Weighting:** if RapidAPI offers per-endpoint "objects/units", set `/v1/broken-links` = 5 and `/v1/pdf-extract` = 5 requests; all others = 1.
- **Benchmark:** the comparable "Website Technology Detector Pro" charges $9.99 for 1,000 requests and $29.99 for 5,000. We give 2× the quota and four extra tools.
- **Economics:** RapidAPI keeps 25%. PayPal takes ≤ 2% (max $20). Payout lands about 5–9 weeks after month end.

## Tags
website audit, seo, tech stack, wappalyzer, builtwith alternative, web scraping, html to markdown, rag, llm, broken links, ssl checker, dns, spf, dmarc, ocr, pdf to text, hebrew ocr
