"""Run: pytest -q            (offline-safe tests)
       LIVE=1 pytest -q     (also hits real public websites)"""
import base64
import json
import os

import pytest
from fastapi.testclient import TestClient

from app.main import TOOLS, app

c = TestClient(app)
RAPID = {'X-RapidAPI-Proxy-Secret': 'test-proxy-secret'}
live = pytest.mark.skipif(os.environ.get('LIVE') != '1', reason='set LIVE=1 for network tests')


def test_meta():
    assert c.get('/health').json()['status'] == 'ok'
    paths = c.get('/openapi.json').json()['paths']
    for path, *_ in TOOLS.values():
        assert f'/v1{path}' in paths and f'/x402/v1{path}' in paths
    assert set(c.get('/pricing').json()['x402']) == set(TOOLS)


@pytest.mark.parametrize('headers', [{}, {'X-RapidAPI-Proxy-Secret': 'wrong'}, {'X-API-Key': 'nope'},
                                     {'X-Zyla-Secret': 'wrong'}, {'X-ApiMarket-Secret': 'wrong'},
                                     {'X-ApiMarket-Secret': 'test-zyla-secret'}])
def test_marketplace_auth_rejects(headers):
    r = c.post('/v1/markdown', json={'url': 'https://example.com'}, headers=headers)
    assert r.status_code == 401


@pytest.mark.parametrize('headers', [RAPID, {'X-Zyla-Secret': 'test-zyla-secret'},
                                     {'X-ApiMarket-Secret': 'test-apimarket-secret'}, {'X-API-Key': 'k1'}])
def test_marketplace_auth_accepts_each_channel(headers):
    # Auth passes, then the SSRF guard answers 422 without touching the network.
    r = c.post('/v1/markdown', json={'url': 'http://127.0.0.1/'}, headers=headers)
    assert r.status_code == 422, r.text


def test_validation_and_ssrf_guard():
    assert c.post('/v1/markdown', json={}, headers=RAPID).status_code == 422
    assert c.post('/v1/broken-links', json={'url': 'example.com', 'max_pages': 500}, headers=RAPID).status_code == 422
    for url in ('http://127.0.0.1/', 'http://169.254.169.254/latest/meta-data/', 'http://localhost:8080'):
        r = c.post('/v1/markdown', json={'url': url}, headers={'X-API-Key': 'k2'})
        assert r.status_code == 422, (url, r.text)


@pytest.mark.parametrize('name', list(TOOLS))
def test_x402_requires_payment(name):
    path, _m, _h, price, _s = TOOLS[name]
    r = c.post(f'/x402/v1{path}', json={'url': 'https://example.com'})
    assert r.status_code == 402
    req = json.loads(base64.b64decode(r.headers['payment-required']))
    acc = req['accepts'][0]
    assert acc['payTo'].lower() == os.environ['X402_PAY_TO'].lower()
    assert acc['network'] == 'eip155:84532'
    assert int(acc['amount']) == round(float(price.strip('$')) * 1_000_000)  # USDC has 6 decimals
    assert req['extensions']['bazaar']['info']['input']['method'] == 'POST'
    assert req['resource']['url'] == f'https://api.example.test/x402/v1{path}'


def test_x402_rejects_garbage_payment():
    r = c.post('/x402/v1/markdown', json={'url': 'https://example.com'},
               headers={'PAYMENT-SIGNATURE': base64.b64encode(b'{"x402Version":2}').decode()})
    assert r.status_code in (400, 402)


@live
def test_live_markdown():
    r = c.post('/v1/markdown', json={'url': 'https://example.com', 'chunk_size': 100}, headers=RAPID)
    assert r.status_code == 200, r.text
    j = r.json()
    assert 'Example Domain' in j['markdown'] and j['chunks']


@live
def test_live_health_audit():
    r = c.post('/v1/health-audit', json={'url': 'example.com'}, headers=RAPID)
    assert r.status_code == 200, r.text
    j = r.json()
    assert 0 <= j['score'] <= 100 and j['http']['status'] == 200 and j['ssl']['valid']


@live
def test_live_tech_detect():
    r = c.post('/v1/tech-detect', json={'url': 'wordpress.org'}, headers=RAPID)
    assert r.status_code == 200, r.text
    names = {t['name'] for t in r.json()['technologies']}
    assert 'WordPress' in names, names


@live
def test_live_broken_links():
    r = c.post('/v1/broken-links', json={'url': 'https://example.com', 'max_pages': 2}, headers=RAPID)
    assert r.status_code == 200, r.text
    assert r.json()['summary']['pagesCrawled'] >= 1


@live
def test_live_pdf():
    r = c.post('/v1/pdf-extract', json={'url': 'https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf'},
               headers=RAPID)
    assert r.status_code == 200, r.text
    assert 'Dummy PDF' in r.json()['content']


def test_get_variants_exist_only_on_v1():
    spec = c.get('/openapi.json').json()['paths']
    for path, *_ in TOOLS.values():
        assert 'get' in spec[f'/v1{path}'] and 'post' in spec[f'/v1{path}']
        assert 'get' not in spec.get(f'/x402/v1{path}', {})


def test_get_auth_and_validation():
    assert c.get('/v1/markdown', params={'url': 'https://example.com'}).status_code == 401
    zyla = {'X-Zyla-Secret': 'test-zyla-secret'}
    assert c.get('/v1/markdown', headers=zyla).status_code == 422  # url missing
    assert c.get('/v1/broken-links', params={'url': 'example.com', 'max_pages': '500'}, headers=zyla).status_code == 422
    assert c.get('/v1/tech-detect', params={'url': 'http://127.0.0.1/'}, headers=zyla).status_code == 422  # SSRF guard
    assert c.get('/v1/pdf-extract', params={'url': 'http://localhost/a.pdf', 'languages': 'eng,heb'},
                 headers=zyla).status_code == 422


def test_query_parsing():
    from starlette.requests import Request
    from app.main import _query_to_dict
    from app.models import PdfIn
    req = Request({'type': 'http', 'query_string': b'url=x.com&languages=eng,heb&languages=ara&max_pages=3&foo=1&mode=&output='})
    m = PdfIn.model_validate(_query_to_dict(PdfIn, req))
    assert m.languages == ['eng', 'heb', 'ara'] and m.max_pages == 3
