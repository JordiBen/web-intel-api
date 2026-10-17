# RapidAPI listing: "Web Intelligence API" (ready to paste)

**Name:** Web Intelligence API
**Category:** Data (secondary: Tools)
**Short description (≤ 100 chars):** Website audit, tech-stack detection, page-to-Markdown, broken links & PDF/OCR in one API.

**Long description:**
Five website and document tools behind one key:
- **/v1/health-audit**: HTTP status, redirect chain, SSL expiry, SPF/DMARC/MX, security headers, SEO basics, and a 0–100 score with a prioritized issue list.
- **/v1/tech-detect**: CMS, e-commerce, frameworks, analytics, CDN, hosting and email provider, from 3,000+ open fingerprints (HTTP Archive / Wappalyzer data), with versions and confidence.
- **/v1/markdown**: any article or page converted to clean Markdown for LLMs and RAG, with title, author and date, plus optional token-sized chunks.
- **/v1/broken-links**: crawls up to 50 pages and reports every broken link and the page it was found on. Respects robots.txt.
- **/v1/pdf-extract**: text and tables from PDFs and images, with OCR for scanned pages in English, Hebrew, Arabic, German, French and Spanish. Fixes RTL text.

Open source (GPL-3.0), built for agencies, SEO tools, lead-gen enrichment and AI agents.
An MCP server package (`web-intel-mcp`) is available for Claude, Cursor and other agents.

**Base URL:** `https://web-intel-api.onrender.com` (set after deploy)
**Spec to import:** `listing/openapi.rapidapi.json`
**Gateway:** copy the *Proxy Secret* into the Render env var `RAPIDAPI_PROXY_SECRET`. Calls that bypass RapidAPI get a 401.

## Plans (benchmarked against "Website Technology Detector Pro": $9.99 for 1k, $29.99 for 5k)
| Plan | Price/mo | Requests/mo | Overage | Rate limit |
|---|---|---|---|---|
| Basic | $0 | 50 | hard limit | 1 req/s |
| Pro | $9.99 | 2,000 | $0.005 | 3 req/s |
| Ultra | $29.99 | 10,000 | $0.004 | 5 req/s |
| Mega | $99 | 50,000 | $0.003 | 10 req/s |

Broken-links and pdf-extract cost more to run, so count each call as **5 requests** (RapidAPI "objects/units" per endpoint).

## Mirror on Zyla API Hub (same spec, same backend)
Zyla takes 20% and pays by PayPal about 60 days after the customer pays. Use header `X-Zyla-Secret`, value in env `ZYLA_SECRET`.
