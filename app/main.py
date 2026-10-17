"""Web Intelligence API: one service, several sales channels.

  /v1/*        -> sold through API marketplaces (RapidAPI, Zyla). Auth: marketplace proxy secret or direct API key.
  /x402/v1/*   -> sold per call to AI agents / developers via x402 (USDC on Base). Auth: the payment itself.
  /mcp         -> remote MCP server (streamable HTTP) exposing the same tools; see mcp_server/.

Environment:
  RAPIDAPI_PROXY_SECRET   secret RapidAPI adds as X-RapidAPI-Proxy-Secret (blocks calls that bypass the marketplace)
  ZYLA_SECRET             optional; same idea for Zyla (header X-Zyla-Secret)
  API_KEYS                optional comma-separated keys accepted in X-API-Key (direct customers / monitoring)
  X402_PAY_TO             EVM address that receives USDC. If unset the /x402 routes are not mounted.
  X402_NETWORK            eip155:8453 (Base mainnet, default) or eip155:84532 (Base Sepolia testnet)
  X402_FACILITATOR_URL    default https://facilitator.payai.network (no API key needed for the free allowance)
  PUBLIC_BASE_URL         e.g. https://web-intel-api.onrender.com (used in discovery metadata)
"""
from __future__ import annotations

import hmac
import logging
import os
from typing import Any, Awaitable, Callable

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from . import service as svc
from .models import AuditIn, LinksIn, MarkdownIn, PdfIn, TechIn

log = logging.getLogger('webapi')
VERSION = '1.0.0'

# name -> (path, request model, handler, x402 price USD, summary)
TOOLS: dict[str, tuple[str, type, Callable[[Any], Awaitable[dict]], str, str]] = {
    'health_audit': ('/health-audit', AuditIn, svc.health_audit, '$0.01',
                     'Website health audit: HTTP, redirects, SSL expiry, DNS/SPF/DMARC, security headers, SEO basics, 0-100 score'),
    'tech_detect': ('/tech-detect', TechIn, svc.tech_detect, '$0.01',
                    'Detect the technology stack of a website (CMS, frameworks, analytics, CDN, hosting, email provider) - 3,000+ fingerprints'),
    'page_markdown': ('/markdown', MarkdownIn, svc.page_markdown, '$0.005',
                      'Convert a web page into clean Markdown for LLMs/RAG (main-content extraction, metadata, optional chunks)'),
    'broken_links': ('/broken-links', LinksIn, svc.broken_links, '$0.03',
                     'Crawl up to 50 pages of a site and report broken links (404/5xx/DNS/timeouts) with the page they were found on'),
    'pdf_extract': ('/pdf-extract', PdfIn, svc.pdf_extract, '$0.02',
                    'Extract text and tables from a PDF or image URL, with OCR for scanned pages (up to 20 pages, Hebrew/Arabic RTL aware)'),
}


def _secret_ok(given: str | None, expected: str | None) -> bool:
    return bool(given and expected and hmac.compare_digest(given.encode(), expected.encode()))


async def marketplace_auth(x_rapidapi_proxy_secret: str | None = Header(None, include_in_schema=False),
                           x_zyla_secret: str | None = Header(None, include_in_schema=False),
                           x_api_key: str | None = Header(None, include_in_schema=False)) -> str:
    if _secret_ok(x_rapidapi_proxy_secret, os.environ.get('RAPIDAPI_PROXY_SECRET')):
        return 'rapidapi'
    if _secret_ok(x_zyla_secret, os.environ.get('ZYLA_SECRET')):
        return 'zyla'
    keys = [k.strip() for k in os.environ.get('API_KEYS', '').split(',') if k.strip()]
    if x_api_key and any(_secret_ok(x_api_key, k) for k in keys):
        return 'direct'
    if os.environ.get('DEV_OPEN_ACCESS') == '1':
        return 'dev'
    raise HTTPException(401, 'Subscribe on RapidAPI, or pay per call via x402 at /x402/v1/*. See /docs.')


def _make_router(prefix: str, deps: list) -> APIRouter:
    r = APIRouter(prefix=prefix, dependencies=deps)
    for name, (path, model, handler, _price, summary) in TOOLS.items():
        def bind(model=model, handler=handler):
            async def endpoint(body: model) -> dict:  # type: ignore[valid-type]
                try:
                    return await handler(body)
                except svc.UserInputError as e:
                    raise HTTPException(422, str(e)) from e
            endpoint.__annotations__ = {'body': model, 'return': dict}  # resolve despite postponed annotations
            return endpoint
        r.add_api_route(path, bind(), methods=['POST'], name=f'{prefix}:{name}', summary=summary,
                        tags=['x402 pay-per-call' if 'x402' in prefix else 'tools'])
    return r


def _x402_routes(pay_to: str, network: str, base: str) -> dict:
    from x402.extensions.bazaar import declare_discovery_extension
    from x402.http import PaymentOption
    from x402.http.types import RouteConfig

    routes = {}
    for name, (path, model, _h, price, summary) in TOOLS.items():
        schema = model.model_json_schema()
        example = {k: (v.get('examples') or [v.get('default')])[0] for k, v in schema['properties'].items()
                   if 'examples' in v}
        routes[f'POST /x402/v1{path}'] = RouteConfig(
            accepts=[PaymentOption(scheme='exact', pay_to=pay_to, price=price, network=network)],
            description=summary, mime_type='application/json', service_name='Web Intel API',
            tags=['web', 'seo', 'scraping', 'markdown', 'ocr'][:5],
            resource=f'{base}/x402/v1{path}' if base else None,
            extensions=declare_discovery_extension(
                input=example, input_schema={'properties': schema['properties'], 'required': schema.get('required', [])},
                body_type='json'),
        )
    return routes


def create_app() -> FastAPI:
    app = FastAPI(title='Web Intelligence API', version=VERSION,
                  description='Website audit, tech-stack detection, page-to-Markdown, broken-link crawl and PDF/OCR '
                              'extraction in one API. Open source: https://github.com/JordiBen')

    @app.get('/', include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse('/docs')

    @app.get('/healthz', tags=['meta'])
    async def healthz() -> dict:
        return {'status': 'ok', 'version': VERSION}

    @app.get('/pricing', tags=['meta'])
    async def pricing() -> dict:
        return {'x402': {n: {'path': f'/x402/v1{t[0]}', 'priceUsd': t[3], 'network': os.environ.get('X402_NETWORK', 'eip155:8453'),
                             'asset': 'USDC'} for n, t in TOOLS.items()},
                'marketplaces': ['RapidAPI (subscription plans)']}

    app.include_router(_make_router('/v1', [Depends(marketplace_auth)]))

    pay_to = os.environ.get('X402_PAY_TO')
    if pay_to:
        from x402.http import FacilitatorConfig, HTTPFacilitatorClient
        from x402.http.middleware.fastapi import PaymentMiddlewareASGI
        from x402.mechanisms.evm.exact import ExactEvmServerScheme
        from x402.server import x402ResourceServer

        network = os.environ.get('X402_NETWORK', 'eip155:8453')
        facilitator = HTTPFacilitatorClient(FacilitatorConfig(
            url=os.environ.get('X402_FACILITATOR_URL', 'https://facilitator.payai.network')))
        server = x402ResourceServer(facilitator)
        server.register(network, ExactEvmServerScheme())
        app.include_router(_make_router('/x402/v1', []))
        app.add_middleware(PaymentMiddlewareASGI,
                           routes=_x402_routes(pay_to, network, os.environ.get('PUBLIC_BASE_URL', '').rstrip('/')),
                           server=server)
        log.info('x402 enabled: pay_to=%s network=%s', pay_to, network)

    @app.exception_handler(Exception)
    async def unhandled(_req: Request, exc: Exception) -> JSONResponse:
        log.exception('unhandled error')
        return JSONResponse({'detail': f'internal error: {type(exc).__name__}'}, status_code=500)

    return app


app = create_app()
