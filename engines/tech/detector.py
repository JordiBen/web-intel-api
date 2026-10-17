"""Static website technology detection using Wappalyzer-format fingerprints (HTTP Archive fork, GPL-3.0).

Covers: headers, cookies, html, scriptSrc, scripts (inline), meta, url, dom (CSS selector existence/attributes/text),
text, dns (via DNS-over-HTTPS), certIssuer, implies / requires / requiresCategory / excludes, versions & confidence.
JavaScript-global ('js') and XHR fingerprints need a real browser and are not evaluated.
"""
from __future__ import annotations

import json
import pathlib
import re
from dataclasses import dataclass, field
from typing import Any

import regex as rx  # supports per-search timeouts (protects against catastrophic backtracking)
from bs4 import BeautifulSoup

DATA = pathlib.Path(__file__).resolve().parents[1] / 'data'
HTML_SCAN_LIMIT = 600_000  # chars of HTML checked by 'html'/'text' regexes


REGEX_TIMEOUT_S = 0.25
SCRIPT_SCAN_LIMIT = 100_000  # chars per inline script


class SafeRegex:
    """Wrapper with a time-boxed search; a timeout counts as 'no match'."""

    __slots__ = ('_r', 'pattern')

    def __init__(self, src: str):
        # A leading '.+' / '.*' adds nothing to a search() but makes it O(n^2) on long inputs.
        stripped = re.sub(r'^(?:\.[+*]\??)+', '', src)
        self._r = rx.compile(stripped, rx.I | rx.V0)
        self.pattern = src

    def search(self, s: str):
        try:
            return self._r.search(s, timeout=REGEX_TIMEOUT_S)
        except TimeoutError:
            return None


@dataclass
class Pattern:
    regex: SafeRegex | None
    version: str | None = None
    confidence: int = 100


def parse_pattern(raw: str) -> Pattern | None:
    parts = str(raw).split('\\;')
    src, version, conf = parts[0], None, 100
    for p in parts[1:]:
        if p.startswith('version:'):
            version = p[8:]
        elif p.startswith('confidence:'):
            try:
                conf = int(p[11:])
            except ValueError:
                pass
    if src == '':
        return Pattern(None, version, conf)  # existence-only pattern
    try:
        # JS regex -> Python: drop possessive/unsupported bits defensively
        return Pattern(SafeRegex(src), version, conf)
    except (rx.error, re.error, ValueError):
        return None


def _plist(v: Any) -> list[Pattern]:
    vals = v if isinstance(v, list) else [v]
    return [p for p in (parse_pattern(x) for x in vals) if p is not None]


def _pdict(v: Any) -> dict[str, list[Pattern]]:
    return {k.lower(): _plist(x) for k, x in (v or {}).items()}


@dataclass
class Tech:
    name: str
    cats: list[int]
    website: str | None
    description: str | None
    icon: str | None
    saas: bool | None
    oss: bool | None
    pricing: list[str]
    cpe: str | None
    headers: dict[str, list[Pattern]] = field(default_factory=dict)
    cookies: dict[str, list[Pattern]] = field(default_factory=dict)
    meta: dict[str, list[Pattern]] = field(default_factory=dict)
    dns: dict[str, list[Pattern]] = field(default_factory=dict)
    html: list[Pattern] = field(default_factory=list)
    text: list[Pattern] = field(default_factory=list)
    script_src: list[Pattern] = field(default_factory=list)
    scripts: list[Pattern] = field(default_factory=list)
    url: list[Pattern] = field(default_factory=list)
    cert_issuer: list[Pattern] = field(default_factory=list)
    dom: list[tuple[str, dict]] = field(default_factory=list)
    implies: list[tuple[str, int]] = field(default_factory=list)
    requires: list[str] = field(default_factory=list)
    requires_category: list[int] = field(default_factory=list)
    excludes: list[str] = field(default_factory=list)


def _names(v: Any) -> list[str]:
    return [str(x).split('\\;')[0] for x in (v if isinstance(v, list) else [v] if v else [])]


def _implies(v: Any) -> list[tuple[str, int]]:
    out = []
    for x in (v if isinstance(v, list) else [v] if v else []):
        parts = str(x).split('\\;')
        conf = 100
        for q in parts[1:]:
            if q.startswith('confidence:'):
                try:
                    conf = int(q[11:])
                except ValueError:
                    pass
        out.append((parts[0], conf))
    return out


def _dom(v: Any) -> list[tuple[str, dict]]:
    if not v:
        return []
    if isinstance(v, str):
        return [(v, {})]
    if isinstance(v, list):
        return [(s, {}) for s in v]
    out = []
    for sel, spec in v.items():
        out.append((sel, spec or {}))
    return out


class Fingerprints:
    def __init__(self, data_dir: pathlib.Path = DATA):
        raw = json.loads((data_dir / 'technologies.json').read_text())
        self.categories = {int(k): v for k, v in json.loads((data_dir / 'categories.json').read_text()).items()}
        self.techs: dict[str, Tech] = {}
        for name, t in raw.items():
            self.techs[name] = Tech(
                name=name, cats=t.get('cats') or [], website=t.get('website'), description=t.get('description'),
                icon=t.get('icon'), saas=t.get('saas'), oss=t.get('oss'), pricing=t.get('pricing') or [],
                cpe=t.get('cpe'), headers=_pdict(t.get('headers')), cookies=_pdict(t.get('cookies')),
                meta=_pdict(t.get('meta')), dns={k.upper(): _plist(v) for k, v in (t.get('dns') or {}).items()},
                html=_plist(t['html']) if 'html' in t else [], text=_plist(t['text']) if 'text' in t else [],
                script_src=_plist(t['scriptSrc']) if 'scriptSrc' in t else [],
                scripts=_plist(t['scripts']) if 'scripts' in t else [], url=_plist(t['url']) if 'url' in t else [],
                cert_issuer=_plist(t['certIssuer']) if 'certIssuer' in t else [], dom=_dom(t.get('dom')),
                implies=_implies(t.get('implies')), requires=_names(t.get('requires')),
                requires_category=list(t.get('requiresCategory') or []) if isinstance(t.get('requiresCategory'), list)
                else ([t['requiresCategory']] if t.get('requiresCategory') else []),
                excludes=_names(t.get('excludes')))

    def category_names(self, ids: list[int]) -> list[str]:
        return [self.categories[i]['name'] for i in ids if i in self.categories]


def _version(p: Pattern, m: re.Match | None) -> str | None:
    if not p.version or m is None:
        return None
    v = p.version

    def grp(i: int) -> str:
        try:
            return m.group(i) or ''
        except (IndexError, re.error):
            return ''
    # ternary syntax: \1?a:b
    def tern(mm: re.Match) -> str:
        return mm.group(2) if grp(int(mm.group(1))) else mm.group(3)
    v = re.sub(r'\\(\d)\?([^:]*):(.*)$', tern, v)
    v = re.sub(r'\\(\d)', lambda mm: grp(int(mm.group(1))), v).strip()
    return v or None


@dataclass
class PageSignals:
    url: str
    headers: dict[str, str]          # lower-case names
    cookies: dict[str, str]          # lower-case names
    html: str
    dns: dict[str, list[str]] = field(default_factory=dict)  # 'MX'/'TXT'/'NS'/... -> values
    cert_issuer: str | None = None


def extract_signals_from_html(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html or '', 'lxml')
    script_src = [s['src'] for s in soup.find_all('script', src=True)]
    scripts = [s.get_text()[:SCRIPT_SCAN_LIMIT] for s in soup.find_all('script', src=False)][:200]
    meta: dict[str, list[str]] = {}
    for m in soup.find_all('meta'):
        key = (m.get('name') or m.get('property') or m.get('http-equiv') or '').lower()
        if key and m.get('content') is not None:
            meta.setdefault(key, []).append(m['content'])
    text = soup.get_text(' ', strip=True)[:HTML_SCAN_LIMIT]
    return {'soup': soup, 'scriptSrc': script_src, 'scripts': scripts, 'meta': meta, 'text': text}


def detect(fp: Fingerprints, sig: PageSignals) -> list[dict[str, Any]]:
    parsed = extract_signals_from_html(sig.html)
    soup = parsed['soup']
    html = sig.html[:HTML_SCAN_LIMIT]
    found: dict[str, dict[str, Any]] = {}

    def hit(name: str, p: Pattern, m: re.Match | None, via: str) -> None:
        cur = found.setdefault(name, {'confidence': 0, 'version': None, 'via': set()})
        cur['confidence'] = min(100, cur['confidence'] + p.confidence)
        v = _version(p, m)
        if v and (cur['version'] is None or len(v) > len(cur['version'])):
            cur['version'] = v
        cur['via'].add(via)

    def match_any(pats: list[Pattern], values: list[str], name: str, via: str) -> None:
        for p in pats:
            for val in values:
                if p.regex is None:
                    hit(name, p, None, via)
                    break
                m = p.regex.search(val)
                if m:
                    hit(name, p, m, via)
                    break

    for t in fp.techs.values():
        for h, pats in t.headers.items():
            if h in sig.headers:
                match_any(pats, [sig.headers[h]], t.name, 'headers')
        for c, pats in t.cookies.items():
            if c in sig.cookies:
                match_any(pats, [sig.cookies[c]], t.name, 'cookies')
            elif c.endswith('*') or '*' in c:  # wildcard cookie names (rare)
                rx = re.compile('^' + re.escape(c).replace(r'\*', '.*') + '$')
                vals = [v for k, v in sig.cookies.items() if rx.match(k)]
                if vals:
                    match_any(pats, vals, t.name, 'cookies')
        for name, pats in t.meta.items():
            if name in parsed['meta']:
                match_any(pats, parsed['meta'][name], t.name, 'meta')
        if t.script_src and parsed['scriptSrc']:
            match_any(t.script_src, parsed['scriptSrc'], t.name, 'scriptSrc')
        if t.scripts and parsed['scripts']:
            match_any(t.scripts, parsed['scripts'], t.name, 'scripts')
        if t.html:
            match_any(t.html, [html], t.name, 'html')
        if t.text:
            match_any(t.text, [parsed['text']], t.name, 'text')
        if t.url:
            match_any(t.url, [sig.url], t.name, 'url')
        if t.cert_issuer and sig.cert_issuer:
            match_any(t.cert_issuer, [sig.cert_issuer], t.name, 'certIssuer')
        for rtype, pats in t.dns.items():
            if sig.dns.get(rtype):
                match_any(pats, sig.dns[rtype], t.name, 'dns')
        for sel, spec in t.dom:
            try:
                els = soup.select(sel, limit=5)
            except Exception:  # noqa: BLE001 - selector unsupported by soupsieve
                continue
            if not els:
                continue
            if not spec or spec.get('exists') is not None:
                hit(t.name, Pattern(None), None, 'dom')
                continue
            for attr, pat in (spec.get('attributes') or {}).items():
                p = parse_pattern(pat)
                for el in els:
                    val = el.get(attr)
                    val = ' '.join(val) if isinstance(val, list) else val
                    if val is not None and p and (p.regex is None or p.regex.search(val)):
                        hit(t.name, p, p.regex.search(val) if p.regex else None, 'dom')
                        break
            if spec.get('text') is not None:
                p = parse_pattern(spec['text'])
                for el in els:
                    txt = el.get_text(' ', strip=True)
                    if p and (p.regex is None or p.regex.search(txt)):
                        hit(t.name, p, p.regex.search(txt) if p.regex else None, 'dom')
                        break

    # implies (transitive)
    changed = True
    while changed:
        changed = False
        for name in list(found):
            for target, pconf in fp.techs[name].implies:
                if target not in fp.techs:
                    continue
                conf = min(found[name]['confidence'], pconf)
                if target not in found:
                    found[target] = {'confidence': conf, 'version': None, 'via': {f'implied by {name}'}}
                    changed = True
    # requires / requiresCategory / excludes
    for name in list(found):
        t = fp.techs[name]
        if t.requires and not any(r in found for r in t.requires):
            found.pop(name, None)
        elif t.requires_category and not any(set(fp.techs[o].cats) & set(t.requires_category) for o in found if o != name):
            found.pop(name, None)
    for name in list(found):
        for ex in fp.techs[name].excludes if name in found else []:
            found.pop(ex, None)

    out = []
    for name, info in found.items():
        t = fp.techs[name]
        out.append({'name': name, 'version': info['version'], 'confidence': info['confidence'],
                    'categories': fp.category_names(t.cats), 'website': t.website,
                    'saas': t.saas, 'oss': t.oss, 'pricing': t.pricing, 'cpe': t.cpe,
                    'detectedVia': sorted(info['via'])})
    out.sort(key=lambda r: (r['categories'][:1], r['name']))
    return out
