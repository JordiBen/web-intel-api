"""Write listing/openapi.rapidapi.json: only the /v1 marketplace routes, server = deployed host."""
import json, os, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
os.environ.pop('X402_PAY_TO', None)
from app.main import app  # noqa: E402
spec = app.openapi()
spec['paths'] = {p: v for p, v in spec['paths'].items() if p.startswith('/v1/')}
spec['servers'] = [{'url': os.environ.get('PUBLIC_BASE_URL', 'https://web-intel-api.onrender.com')}]
out = pathlib.Path(__file__).resolve().parents[1] / 'listing' / 'openapi.rapidapi.json'
out.write_text(json.dumps(spec, indent=2))
print(out, len(spec['paths']), 'paths')
