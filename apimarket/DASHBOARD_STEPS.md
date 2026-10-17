# API.market: publish "Web Intelligence API" from the Seller Console

Why the dashboard: API.market has no public seller API. Its docs (docs.api.market/llms.txt) only offer buyer APIs
(subscriptions, usage), and the key in APIMARKET_API_KEY is a buyer key (`x-api-market-key`). Everything below
takes about 15 minutes in https://api.market/seller -> Seller Console.

Spec URL (public, raw GitHub):
`https://raw.githubusercontent.com/JordiBen/web-intel-api/main/apimarket/openapi.apimarket.json`
(If the import asks for a file instead of a URL, open that link, press Ctrl+S, and upload the saved file.)

## 1. Organization (store)
- Seller Console -> **Start** next to *Create organization*
- **Name:** `WebIntel Tools` -> **Create Organization**
- Later, under Settings -> Store Settings: **Slug** `webintel-tools`. **Description:**
  `Developer APIs for website intelligence: audits, tech-stack detection, page-to-Markdown, broken links and PDF OCR. Built with AI assistance and tested on live websites.`

## 2. API Source (Manage APIs -> OpenAPI Specs -> Import)
1. Upload/import the spec above. You should see 5 paths: `/v1/health-audit`, `/v1/tech-detect`, `/v1/markdown`, `/v1/broken-links`, `/v1/pdf-extract` (all POST).
2. **Custom headers:** `{"Content-Type": "application/json"}`
3. **Base URL:** `https://web-intel-api.onrender.com` (pre-filled from the spec. Do NOT add /v1, because the paths already have it.)
4. **Authentication:** tab **API Key**
   - Header Name: `X-ApiMarket-Secret`
   - API Key Value: the secret Grok Bot gives you separately (`APIMARKET_SECRET`). Never post it in a chat or the listing text.
5. Review the summary -> **Create API Source**.

## 3. API Product (Create Product on the green banner)
- **Product slug:** `web-intelligence-api` (it can't be changed later)
- **Title:** `Web Intelligence API: Website Audit, Tech Stack, Markdown, Broken Links & OCR`
- **Subtitle (max 160):** `Audit websites, detect tech stacks, convert pages to Markdown, find broken links and OCR PDFs. One key, JSON in and out.`
- **Categories:** Data / Web Scraping / SEO / Tools (pick the closest available)
- **Tags (if asked):** website audit, seo, tech stack, wappalyzer alternative, builtwith alternative, html to markdown, rag, llm, broken links, ssl, dns, ocr, pdf to text
- **Description (markdown):** paste the block below.

```markdown
## About the API
Web Intelligence API bundles five website and document tools behind one subscription. Send a URL as JSON and get structured JSON back.

| Endpoint | Input | Output |
|---|---|---|
| Website Health Audit | domain or URL | HTTP status, redirects, response time, SSL validity and days to expiry, SPF/DMARC/MX/NS, security headers, SEO basics (title, meta description, H1, canonical, robots.txt, sitemap) and a 0-100 score with prioritized issues |
| Tech Stack Detection | domain or URL | CMS, e-commerce, frameworks, analytics, tag managers, CDN, hosting, email and DNS providers, with versions and confidence (3,000+ open fingerprints) |
| Page to Markdown | page URL | main content as clean Markdown with title, author, date and language, plus optional RAG chunks |
| Broken Link Finder | domain or URL | crawls up to 50 pages and lists broken links (404, 5xx, DNS, timeouts) with the page and anchor text where each was found |
| PDF & Image Text Extraction | PDF or image URL | text and tables, with OCR for scanned pages in English, Hebrew, Arabic, German, French and Spanish (RTL fixed), up to 20 pages |

## Example
POST /v1/tech-detect with body {"url": "wordpress.org"} returns the detected technologies with categories, versions and confidence.

## Common use cases
- Agencies: audit a prospect's website before a sales call.
- Lead generation: enrich company lists with their tech stack (BuiltWith / Wappalyzer alternative).
- AI and RAG: feed clean Markdown of any web page to an LLM.
- Monitoring: catch broken links and expiring SSL certificates.
- Back office: get text out of scanned PDFs and invoices.

## Limitations
- Public websites only; private and internal addresses are blocked.
- Broken Link Finder: max 50 pages per call. PDF extraction: max 20 pages per call.
- Heavy calls (broken links, OCR) can take 10-100 seconds.
- The tool respects robots.txt. Sites that block automated checks are reported as "blocked", not "broken".

## About us
Built and maintained by WebIntel Tools. The service was developed with AI assistance and is tested against live websites.
Every endpoint is also available to AI agents through API.market's automatic MCP endpoint.
```
Click **Save**.

## 4. Pricing plans (Manage Pricing Plans -> Add Pricing Plans, 4 times)
For every plan: API source = the one from step 2. Billing unit = **Per call**. Endpoints = **Select all**. Access = **Public**.
Under *Advanced: custom headers and rate limit*, leave custom headers empty and set the rate limit as shown (API.market counts per second).

| Plan name | Plan type | Price | Included calls | When they run out | Rate limit (req/s) |
|---|---|---|---|---|---|
| Free | Free trial | $0 | 50 | (stops) | 1 |
| Basic | Monthly subscription | $9.99 | 2,000 / month | Stop the calls | 2 |
| Pro | Monthly subscription | $29.99 | 10,000 / month | Stop the calls | 3 |
| Business | Monthly subscription | $99 | 50,000 / month | Stop the calls | 4 |

(1/2/3/4 req/s = the same 60/120/180/240 per minute we use on Zyla. On API.market a free plan is always a 7-day trial; a monthly free plan only exists as a private plan.)

## 5. Test, then submit
1. On the product page, test **Tech Stack Detection** in the API Playground with `{"url":"wordpress.org"}`. Expect 200. The first call can take 30-60 s while the server wakes up.
2. Checklist shows **3/3** -> click **Send for Review**. Review takes 1-3 business days; the result comes by email.
3. Payout: Settings -> payout details (PayPal or bank).

Send Grok Bot a screenshot after steps 2, 4 and 5 if anything looks different.
