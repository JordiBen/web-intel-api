"""Write per-marketplace OpenAPI files with only the /v1 routes and server = deployed host.

  python tools/export_openapi.py            -> listing/openapi.rapidapi.json (unchanged behaviour)
  python tools/export_openapi.py zyla       -> zyla/openapi.zyla.json
  python tools/export_openapi.py apimarket  -> apimarket/openapi.apimarket.json
"""
import json, os, sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.pop('X402_PAY_TO', None)
from app.main import app  # noqa: E402

target = sys.argv[1] if len(sys.argv) > 1 else 'rapidapi'
spec = app.openapi()
spec['paths'] = {p: v for p, v in spec['paths'].items() if p.startswith('/v1/')}
spec['servers'] = [{'url': os.environ.get('PUBLIC_BASE_URL', 'https://web-intel-api.onrender.com')}]
out = {'rapidapi': ROOT / 'listing' / 'openapi.rapidapi.json',
       'zyla': ROOT / 'zyla' / 'openapi.zyla.json',
       'apimarket': ROOT / 'apimarket' / 'openapi.apimarket.json'}[target]
if target != 'rapidapi':
    extra = json.loads((ROOT / 'tools' / 'openapi_extras.json').read_text())
    spec['info'].update(extra['info'])
    spec['tags'] = extra['tags']
    for path, ops in spec['paths'].items():
        e = extra['paths'].get(path, {})
        for op in ops.values():
            op['tags'] = [e.get('tag', 'tools')]
            op['operationId'] = e['operationId']
            op['summary'] = e['summary']
            op['description'] = e['description']
            if 'example' in e:
                op['requestBody']['content']['application/json']['example'] = e['example']
            if 'response' in e:
                op['responses']['200']['content']['application/json']['example'] = e['response']
            op['responses']['401'] = {'description': 'Request did not come through the marketplace'}
            op['responses']['429'] = {'description': 'Plan quota or rate limit reached'}
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(spec, indent=2, ensure_ascii=False))
print(out, len(spec['paths']), 'paths')
