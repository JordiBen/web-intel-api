# API.market listing: Web Intelligence API

Status: ready to import once the API.market seller account exists (https://api.market/seller -> Seller Console).
Order in the Seller Console: Organization/store -> API Source (import OpenAPI) -> API Product -> Pricing plans -> Submit for review -> Payout details.

## 1. Store details
- **Store / organization name:** WebIntel Tools
- **Store slug:** webintel-tools
- **Website:** https://jordiben.github.io/
- **Store description:** Developer APIs for website intelligence: audits, tech-stack detection, page-to-Markdown, broken links and PDF OCR. Built with AI assistance and tested on live websites.

## 2. API Source (Manage APIs -> OpenAPI Specs -> Import)
- **File:** `openapi.apimarket.json` (validated as OpenAPI 3.1; servers = `https://web-intel-api.onrender.com`)
- **Base URL:** `https://web-intel-api.onrender.com`
- **Authentication tab:** API Key
  - **Header name:** `X-ApiMarket-Secret`
  - **API key value:** the `APIMARKET_SECRET` value in `/workspace/webapi/.secrets.local` (already set on Render)
- **Custom headers:** `{"Content-Type": "application/json"}` (optional)
- **Timeout (if offered):** the maximum. Broken links and OCR can take up to ~110 s.

## 3. API Product
- **Product title:** Web Intelligence API: Website Audit, Tech Stack, Markdown, Broken Links & OCR
- **Product slug:** web-intelligence-api
- **Short description (≤160 chars):** Audit websites, detect tech stacks, convert pages to Markdown, find broken links and OCR PDFs. One key, JSON in and out.
- **Categories:** Data / Web Scraping / SEO (pick the closest available)
- **Tags:** website audit, seo, tech stack, wappalyzer alternative, builtwith alternative, html to markdown, rag, llm, broken links, ssl, dns, ocr, pdf to text
- **Long description:** use the "About the API" block from `../zyla/LISTING.md` section 1 unchanged (same text, same AI-assistance note). Add this line at the end:
  > Every endpoint is also available to AI agents through API.market's automatic MCP endpoint.

## 4. Pricing plans (mirror RapidAPI)
| Plan | Type | Price | Included calls / month | Overage | Rate limit |
|---|---|---|---|---|---|
| Free | subscription | $0 | 50 | none (hard stop) | 1 req/s |
| Basic | subscription | $9.99 | 2,000 | $0.005 / call | 3 req/s |
| Pro | subscription | $29.99 | 10,000 | $0.004 / call | 5 req/s |
| Business | subscription | $99 | 50,000 | $0.003 / call | 10 req/s |
| Pay as you go (optional) | usage | $0.01 / call | – | – | 3 req/s |

API.market fee is up to 20% (vs RapidAPI 25%); prices stay the same everywhere so no marketplace undercuts another.

## 5. Review checklist before "Submit for review"
- Test each endpoint in the API.market Playground after import (expect 200; first call can take ~60 s if Render is asleep).
- Make sure every endpoint shows its example body (they're in the spec).
- Payout: PayPal or bank, monthly, 30 days after the period, $50 minimum.
