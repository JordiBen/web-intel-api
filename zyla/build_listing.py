"""Build zyla/listing.json for PUT https://zylalabs.com/api/listings (secret injected at send time, never stored)."""
import json, sys
sys.path.insert(0, '.')
from app.models import AuditIn, TechIn, MarkdownIn, LinksIn, PdfIn

spec = json.load(open('zyla/openapi.zyla.json'))
B = 'https://web-intel-api.onrender.com/v1'
EPS = [
  ('Website Health Audit', '/health-audit', AuditIn, {'url': 'example.com'},
   'Audit one website: HTTP status, redirects, SSL expiry, DNS/SPF/DMARC, security headers, SEO basics and a 0-100 score with prioritized issues.'),
  ('Tech Stack Detection', '/tech-detect', TechIn, {'url': 'wordpress.org'},
   'Detect the CMS, frameworks, analytics, CDN, hosting and email providers of a website, with versions and confidence scores.'),
  ('Page to Markdown', '/markdown', MarkdownIn, {'url': 'https://en.wikipedia.org/wiki/Markdown'},
   'Convert a web page into clean Markdown of its main content, with title, author, date and language, plus optional RAG chunks.'),
  ('Broken Link Finder', '/broken-links', LinksIn, {'url': 'crawlee.dev', 'max_pages': '10'},
   'Crawl up to 50 pages of a website and list broken links (404, 5xx, DNS, timeouts) with the page and anchor text where each appears.'),
  ('PDF and Image Text Extraction', '/pdf-extract', PdfIn, {'url': 'https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf'},
   'Extract text and tables from a PDF or image URL, with OCR for scanned pages in English, Hebrew, Arabic, German, French and Spanish.'),
]
endpoints = []
for name, path, model, examples, desc in EPS:
    sch = model.model_json_schema(); req = set(sch.get('required', []))
    params = []
    for k, v in sch['properties'].items():
        d = v.get('description') or k.replace('_', ' ').capitalize()
        dflt = v.get('default')
        if v.get('type') == 'boolean':
            d += ' (true or false)'; dflt = str(dflt).lower()
        elif v.get('type') == 'array':
            d = 'OCR language codes, comma-separated: eng, heb, ara, deu, fra, spa'; dflt = ','.join(dflt)
        elif 'enum' in v:
            d += ' (one of: ' + ', '.join(v['enum']) + ')'
        if 'minimum' in v and 'maximum' in v:
            d += f" ({v['minimum']}-{v['maximum']})"
        if len(d) < 10: d += ' option'
        t = 'number' if v.get('type') == 'integer' else 'string'
        # Zyla's validator calls each endpoint with these values, so example inputs are prefilled (customers can edit them)
        if k in examples: d += f'. Example: {examples[k]}'
        elif dflt not in (None, ''): d += f'. Default: {dflt}'
        params.append({'key': k, 'type': t, 'description': d, 'value': str(examples.get(k, '')), 'required': k in req})
    ex = spec['paths']['/v1' + path]['post']['responses']['200']['content']['application/json']['example']
    s = json.dumps(ex)
    assert len(s) <= 10000, (path, len(s))
    endpoints.append({'name': name, 'description': desc, 'method': 'GET', 'base_url': B + path,
                      'parameters': params, 'headers': [{'key': 'Accept', 'value': 'application/json'}],
                      'example_response': ex})
listing = {
  'product_key': 'webintel-web-intelligence-api',
  'publish': True,
  'api': {'name': 'Web Intelligence API',
          'short_description': 'Web Intelligence API audits websites, detects their tech stack, converts pages to Markdown, finds broken links and extracts text from PDFs with OCR, all with one key.',
          'trial': True},
  'access': {'in': 'header', 'key': 'X-Zyla-Secret', 'value': '__SECRET__'},
  'endpoints': endpoints,
  'plans': [
    {'name': 'Free', 'interval': 'Monthly', 'price': 0, 'max_requests': 50, 'rate_limit': 60},
    {'name': 'Basic', 'interval': 'Monthly', 'price': 9.99, 'max_requests': 2000, 'rate_limit': 120},
    {'name': 'Pro', 'interval': 'Monthly', 'price': 29.99, 'max_requests': 10000, 'rate_limit': 180},
    {'name': 'ProPlus', 'interval': 'Monthly', 'price': 99.0, 'max_requests': 50000, 'rate_limit': 240},
  ],
  'faqs': [
    {'question': 'Can I check a bare domain instead of a full URL?', 'answer': 'Yes. Website Health Audit, Tech Stack Detection and Broken Link Finder accept either a bare domain name or a full address that starts with https.'},
    {'question': 'Why do some calls take longer?', 'answer': 'Broken Link Finder crawls up to 50 pages and OCR processes up to 20 pages, so these calls can take 10-100 seconds. The other endpoints usually answer in a few seconds.'},
    {'question': 'Which OCR languages are supported?', 'answer': 'English (eng), Hebrew (heb), Arabic (ara), German (deu), French (fra) and Spanish (spa). Pass them comma-separated in the languages parameter. Right-to-left text is fixed automatically.'},
    {'question': 'Can it access private or internal addresses?', 'answer': 'No. Only public websites are checked; private, local and internal addresses are blocked.'},
    {'question': 'Does it respect robots.txt?', 'answer': 'Yes. Links blocked by robots.txt or by the target site are reported as blocked, not as broken.'},
  ],
}
json.dump(listing, open('zyla/listing.json', 'w'), indent=2)
print('ok', [ (e['name'], len(e['parameters'])) for e in endpoints])
