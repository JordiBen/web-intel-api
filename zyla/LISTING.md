# Zyla API Hub listing: Web Intelligence API

Status: ready to paste once the Zyla provider account exists (https://zylalabs.com/register).
Spec for reference: `openapi.zyla.json` (Zyla adds endpoints by form, one per endpoint; the spec holds every field).
Backend: `https://web-intel-api.onrender.com` (same service as RapidAPI; Zyla calls are authenticated by `X-Zyla-Secret`).

## 1. Name and descriptions
- **API name:** Web Intelligence API
- **Short description:** Web Intelligence API audits websites, detects their tech stack, converts pages to Markdown, finds broken links and extracts text from PDFs with OCR, all with one key.

### Long description (paste as is)
**About the API**
Web Intelligence API bundles five website and document tools behind one subscription. Send a URL as JSON and get structured JSON back.

| Endpoint | Input | Output |
|---|---|---|
| Website Health Audit | domain or URL | HTTP status, redirects, response time, SSL validity and days to expiry, SPF/DMARC/MX/NS, security headers, SEO basics (title, meta description, H1, canonical, robots.txt, sitemap) and a 0-100 score with prioritized issues |
| Tech Stack Detection | domain or URL | CMS, e-commerce, frameworks, analytics, tag managers, CDN, hosting, email and DNS providers, with versions and confidence (3,000+ open fingerprints) |
| Page to Markdown | page URL | main content as clean Markdown with title, author, date and language, plus optional RAG chunks |
| Broken Link Finder | domain or URL | crawls up to 50 pages and lists broken links (404, 5xx, DNS, timeouts) with the page and anchor text where each was found |
| PDF & Image Text Extraction | PDF or image URL | text and tables, with OCR for scanned pages in English, Hebrew, Arabic, German, French and Spanish (RTL fixed), up to 20 pages |

**Common use cases**
- Agencies: audit a prospect's website before a sales call.
- Lead generation: enrich company lists with their tech stack (BuiltWith / Wappalyzer alternative).
- AI and RAG: feed clean Markdown of any web page to an LLM.
- Monitoring: catch broken links and expiring SSL certificates.
- Back office: get text out of scanned PDFs and invoices.

**Limitations**
- Public websites only; private and internal addresses are blocked.
- Broken Link Finder: max 50 pages per call. PDF extraction: max 20 pages per call.
- Heavy calls (broken links, OCR) can take 10-100 seconds.
- The tool respects robots.txt. Some sites block automated checks; those links are reported as "blocked", not "broken".

**About us**
Built and maintained by WebIntel Tools (https://jordiben.github.io/). The service was developed with AI assistance and is tested against live websites.

- **Category:** Data (fallback: Tools)
- **Website:** https://jordiben.github.io/
- **Icon (500x500):** `../../site/` has no icon yet; I can export one from the WebIntel Tools YouTube avatar before submitting.

## 2. Plans (Zyla requires a free plan and a basic plan; mirror RapidAPI so no channel undercuts another)
| Plan | Price / month | Requests / month | Limit type | Rate limit |
|---|---|---|---|---|
| Free trial (Zyla's trial) | $0 | 50 | hard | 1 req/s |
| Basic | $9.99 | 2,000 | hard | 3 req/s |
| Pro | $29.99 | 10,000 | soft (overage) | 5 req/s |
| Pro Plus | $99.00 | 50,000 | soft (overage) | 10 req/s |

If Zyla's price list doesn't offer an exact value, pick the closest option (e.g. $9.99 -> $9.99/$10, $29.99 -> $29.99/$30). Zyla uses the top plan's per-call price for overage.

## 3. Tags
website audit, seo audit, tech stack, technology lookup, wappalyzer alternative, builtwith alternative, html to markdown, web to markdown, rag, broken links, link checker, ssl checker, dns lookup, spf dmarc, ocr, pdf to text, hebrew ocr, lead enrichment

## 4. Access Control -> Authentication (one secret for all endpoints)
- **Name:** `X-Zyla-Secret`
- **Value:** the `ZYLA_SECRET` value in `/workspace/webapi/.secrets.local` (already set on Render; do not paste it anywhere else)
- **Type:** Header
- **Description:** Shared secret that proves the call came through Zyla API Hub.

## 5. Endpoints (Add New Endpoint, five times)
For every endpoint: **Method** POST, **Header** `Content-Type: application/json`, **Body**: the JSON shown (Zyla shows it as editable input), **Cache**: lowest option / no cache (results change over time).

| # | Endpoint name | URL | Body JSON | Description |
|---|---|---|---|---|
| 1 | Website Health Audit | `https://web-intel-api.onrender.com/v1/health-audit` | `{"url":"example.com","check_dns":true,"check_ssl":true,"check_seo":true}` | Audit one website: HTTP, redirects, SSL expiry, DNS/SPF/DMARC, security headers, SEO basics and a 0-100 score with issues. |
| 2 | Tech Stack Detection | `https://web-intel-api.onrender.com/v1/tech-detect` | `{"url":"wordpress.org","min_confidence":50,"with_dns":true}` | Detect CMS, frameworks, analytics, CDN, hosting and email providers of a website, with versions and confidence. |
| 3 | Page to Markdown | `https://web-intel-api.onrender.com/v1/markdown` | `{"url":"https://en.wikipedia.org/wiki/Markdown","mode":"article","include_links":true,"include_images":false,"include_tables":true,"chunk_size":0}` | Convert a web page into clean Markdown (main content), with metadata and optional RAG chunks. |
| 4 | Broken Link Finder | `https://web-intel-api.onrender.com/v1/broken-links` | `{"url":"crawlee.dev","max_pages":10,"check_external":true,"check_resources":false,"include_ok":false}` | Crawl up to 50 pages of a site and list broken links with the page and anchor text where they appear. |
| 5 | PDF & Image Text Extraction | `https://web-intel-api.onrender.com/v1/pdf-extract` | `{"url":"https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf","mode":"auto","languages":["eng"],"output":"markdown","max_pages":20,"extract_tables":true}` | Extract text and tables from a PDF or image URL, with OCR for scanned pages (English, Hebrew, Arabic, German, French, Spanish). |

Parameter documentation per endpoint and a real sample response for each are in `openapi.zyla.json` (`requestBody.content.*.schema` and `responses.200.content.*.example`). Paste the sample response into Zyla's "Response example" field.

## 6. Payout and uptime notes
- Zyla pays 80% at >=99.9% uptime and nothing in a month under 95%. The service runs on Render's free plan, which sleeps after 15 minutes idle and needs ~30-60 s to wake. Calls still succeed, just slowly. When the first paying subscriber arrives, upgrading Render to Starter ($7/mo) removes cold starts (needs Yarden's approval).
- Payout: PayPal, 60 days after the customer pays, processed 20th-30th of the month.
- Don't link RapidAPI customers to Zyla (RapidAPI anti-circumvention clause).
