"""Self keep-alive for Render's free plan.

Render spins a free web service down after 15 minutes without inbound traffic, and the ~1 minute
cold start hurts marketplace uptime scores. While running on Render (env RENDER is set), this task
requests the service's own public /health URL every KEEPALIVE_INTERVAL seconds (default 600).
The request goes out through Render's edge, so it counts as inbound traffic.
Disable with KEEPALIVE=0.
"""
from __future__ import annotations

import asyncio
import logging
import os

import httpx

log = logging.getLogger('webapi.keepalive')


def enabled() -> bool:
    return bool(os.environ.get('RENDER')) and os.environ.get('KEEPALIVE', '1') != '0'


async def run() -> None:
    base = (os.environ.get('PUBLIC_BASE_URL') or os.environ.get('RENDER_EXTERNAL_URL') or '').rstrip('/')
    if not base:
        return
    interval = max(60, int(os.environ.get('KEEPALIVE_INTERVAL', '600')))
    url = f'{base}/health'
    await asyncio.sleep(30)
    async with httpx.AsyncClient(timeout=30, headers={'User-Agent': 'web-intel-api-keepalive'}) as client:
        while True:
            try:
                r = await client.get(url)
                log.info('keepalive %s -> %s', url, r.status_code)
            except Exception as e:  # never let the loop die
                log.warning('keepalive failed: %s', e)
            await asyncio.sleep(interval)
