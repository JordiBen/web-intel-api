# Zyla: publish "Web Intelligence API" from the web dashboard

Why the dashboard: Yarden's key does work with Zyla's provider Listings API (`GET /api/listings/me` -> `listings_api: true`, 0 listings yet).
But that API rejects request bodies (`422 not_supported`, "use the web wizard"), and all 5 of our endpoints are `POST` with a JSON body. So the listing has to be created in the wizard.
Zyla rule to follow: **no website, email or contact details anywhere** in the listing, and no prices or promotional text in descriptions. That's why the "About us" text below has no URL.

## 0. Before you start
- Log in at https://zylalabs.com, then choose **Add new API** from the account menu (top right). This is the same as the "Add your API" button.
- Have the import file ready: `openapi.zyla.import.json`. It's a copy of our spec with the website and contact links removed.
- Have the secret value ready (`ZYLA_SECRET`). Grok Bot gives it to you separately. Never post it in chat or in the listing text.

## 1. Choose the method
Choose **OpenAPI import** and upload `openapi.zyla.import.json`. This creates all 5 endpoints with their bodies and example responses.
If the import fails or skips something, use **Manual** and fill in section 4 below by hand.

## 2. Name and descriptions
- **API name:** `Web Intelligence API`
- **Short description:**
  `Web Intelligence API audits websites, detects their tech stack, converts pages to Markdown, finds broken links and extracts text from PDFs with OCR, all with one key.`
- **Long description:** paste the "About the API", "Common use cases" and "Limitations" sections from LISTING.md §1 as they are. **Replace** the "About us" paragraph with:
  `Built and maintained by WebIntel Tools. The service was developed with AI assistance and is tested against live websites.`
- **Category:** Data (if not available: Tools)
- **Tags:** `website audit, seo audit, tech stack, technology lookup, wappalyzer alternative, builtwith alternative, html to markdown, web to markdown, rag, broken links, link checker, ssl checker, dns lookup, spf dmarc, ocr, pdf to text, hebrew ocr, lead enrichment`
- **Website field:** leave empty (it's against Zyla's rules)
- **Logo:** skip for now if it's optional. Otherwise, upload the WebIntel Tools YouTube avatar (500x500).

## 3. Access Control -> Authentication (where the secret goes)
Once, for the whole API:
- **Name:** `X-Zyla-Secret`
- **Value:** the `ZYLA_SECRET` value
- **Type:** `Header`
- **Description:** `Shared secret that proves the call came through Zyla API Hub.`

Without this, every call gets 401 from our server.

## 4. Endpoints (check them after the import, or add them with "Add New Endpoint" x5)
For each endpoint: **Method** `POST`, **Header** `Content-Type` = `application/json`, **Body**: the JSON below, **Cache**: the lowest option / no cache.
**Response example:** copy `responses.200.content.application/json.example` from `openapi.zyla.import.json` for that path.

| # | Name | Base URL | Body JSON | Description |
|---|---|---|---|---|
| 1 | Website Health Audit | `https://web-intel-api.onrender.com/v1/health-audit` | `{"url":"example.com","check_dns":true,"check_ssl":true,"check_seo":true}` | Audit one website: HTTP, redirects, SSL expiry, DNS/SPF/DMARC, security headers, SEO basics and a 0-100 score with issues. |
| 2 | Tech Stack Detection | `https://web-intel-api.onrender.com/v1/tech-detect` | `{"url":"wordpress.org","min_confidence":50,"with_dns":true}` | Detect CMS, frameworks, analytics, CDN, hosting and email providers of a website, with versions and confidence. |
| 3 | Page to Markdown | `https://web-intel-api.onrender.com/v1/markdown` | `{"url":"https://en.wikipedia.org/wiki/Markdown","mode":"article","include_links":true,"include_images":false,"include_tables":true,"chunk_size":0}` | Convert a web page into clean Markdown (main content), with metadata and optional RAG chunks. |
| 4 | Broken Link Finder | `https://web-intel-api.onrender.com/v1/broken-links` | `{"url":"crawlee.dev","max_pages":10,"check_external":true,"check_resources":false,"include_ok":false}` | Crawl up to 50 pages of a site and list broken links with the page and anchor text where they appear. |
| 5 | PDF & Image Text Extraction | `https://web-intel-api.onrender.com/v1/pdf-extract` | `{"url":"https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf","mode":"auto","languages":["eng"],"output":"markdown","max_pages":20,"extract_tables":true}` | Extract text and tables from a PDF or image URL, with OCR for scanned pages (English, Hebrew, Arabic, German, French, Spanish). |

Test one endpoint (for example #2) with the test button. The first call can take 30-60 seconds because the Render server wakes up.

## 5. Plans (monthly; Zyla requires rate limits of 60-240/min and more calls on every pricier plan)
| Plan name (exact) | Price / month | Requests / month | Rate limit / min | Limit type |
|---|---|---|---|---|
| Free | $0 | 50 | 60 | hard |
| Basic | $9.99 | 2,000 | 120 | hard |
| Pro | $29.99 | 10,000 | 180 | soft / overage, if offered |
| ProPlus | $99.00 | 50,000 | 240 | soft / overage, if offered |

If there's no "Free" plan, keep Zyla's 7-day free trial on (50 requests). That gives the same result.

## 6. Submit
Click **Save / Publish**. Zyla's automatic checks run right away. If something fails, the error says what to fix. Send Grok Bot a screenshot of any error.
Then the Zyla team reviews the listing. After approval: Provider Settings -> add tax information (the W-8BEN details, like ScraperAPI) and the PayPal payout method.
