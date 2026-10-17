# Web Intelligence API

One FastAPI service that reuses the core logic of the five Python Apify Actors
(website-health-audit, website-tech-detector, page-to-markdown, broken-link-checker, pdf-ocr-extractor)
and sells it through several channels at once:

| Channel | Route | How it's paid |
|---|---|---|
| RapidAPI / Zyla / API.market | `POST /v1/*` | Monthly plans; marketplace pays out. Locked by a per-marketplace secret header (`X-RapidAPI-Proxy-Secret`, `X-Zyla-Secret`, `X-ApiMarket-Secret`). Listing kits: `rapidapi/`, `zyla/`, `apimarket/`. |
| AI agents and developers via x402 | `POST /x402/v1/*` | USDC on Base per call ($0.005–$0.03), settled to `X402_PAY_TO`. Failed calls are never charged. Listed in the x402 Bazaar after the first sale. |
| MCP (Claude, Cursor, …) | `mcp_server/` | Thin MCP client of `/v1` (RapidAPI key), listed free on Smithery, mcp.so, Glama and PulseMCP |

```bash
./tools/sync_engines.sh            # refresh engines/ from /workspace/apify/actors
pip install -r requirements.txt
DEV_OPEN_ACCESS=1 uvicorn app.main:app --reload       # http://localhost:8000/docs
pytest -q                                             # offline tests
LIVE=1 ALLOW_PRIVATE_NETWORK_FOR_LOCAL_DEV=1 pytest -q -k live   # real-site tests (box DNS needs the flag)
python tools/export_openapi.py     # listing/openapi.rapidapi.json  (add 'zyla' or 'apimarket' for those specs)
```
Deploy: Render Blueprint (`render.yaml`, Docker, free plan). SSRF guard blocks private and metadata IPs.
License GPL-3.0, because the tech fingerprints are GPL-3.0 (see NOTICE).
