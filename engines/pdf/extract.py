"""Document text extraction: PDF text layer first, Tesseract OCR fallback, optional tables. No Apify dependency."""
from __future__ import annotations

import io
import re
import time
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Iterator

import httpx
import pdfplumber
import pypdfium2 as pdfium
import pytesseract
from PIL import Image, ImageOps

from .netguard import assert_public_url

SUPPORTED_LANGS = ['eng', 'heb', 'ara', 'rus', 'deu', 'fra', 'spa', 'ita', 'por', 'nld', 'pol', 'tur', 'ukr']
RTL_LANGS = {'heb', 'ara'}
MAX_BYTES_DEFAULT = 50 * 1024 * 1024
MIN_TEXT_CHARS = 25  # below this a PDF page is treated as scanned


@dataclass
class ExtractOptions:
    languages: tuple[str, ...] = ('eng',)
    mode: str = 'auto'  # auto | ocr | text
    extract_tables: bool = True
    max_pages: int = 500
    dpi: int = 300
    max_bytes: int = MAX_BYTES_DEFAULT
    allow_private: bool = False
    deadline: float | None = None       # time.monotonic() value; OCR/pages past it are skipped (partial result)
    max_image_pixels: int | None = None # downscale images/rendered pages above this many pixels before OCR
    state: dict = field(default_factory=dict)  # out: {'timeBudgetExceeded': bool}


class DocumentError(Exception):
    pass


def detect_kind(data: bytes) -> str:
    if data[:5] == b'%PDF-':
        return 'pdf'
    sigs = {b'\x89PNG': 'image', b'\xff\xd8\xff': 'image', b'II*\x00': 'image', b'MM\x00*': 'image',
            b'GIF8': 'image', b'BM': 'image'}
    for sig, kind in sigs.items():
        if data.startswith(sig):
            return kind
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'image'
    raise DocumentError('Unsupported file type (expected PDF, PNG, JPEG, TIFF, GIF, BMP or WebP)')


async def download(client: httpx.AsyncClient, url: str, opts: ExtractOptions) -> bytes:
    await assert_public_url(url, allow_private=opts.allow_private)
    async with client.stream('GET', url, follow_redirects=True) as r:
        if r.status_code >= 400:
            raise DocumentError(f'Download failed: HTTP {r.status_code}')
        await assert_public_url(str(r.url), allow_private=opts.allow_private)
        declared = int(r.headers.get('content-length') or 0)
        if declared > opts.max_bytes:
            raise DocumentError(f'File too large ({declared} bytes > {opts.max_bytes})')
        buf = bytearray()
        async for chunk in r.aiter_bytes():
            buf.extend(chunk)
            if len(buf) > opts.max_bytes:
                raise DocumentError(f'File too large (> {opts.max_bytes} bytes)')
    return bytes(buf)


# ------------------------------------------------------------------ text helpers

_HEB_ARA = re.compile(r'[\u0590-\u05FF\u0600-\u06FF]')


def clean_text(s: str) -> str:
    s = unicodedata.normalize('NFC', s or '')
    s = s.replace('\r', '')
    s = re.sub(r'[ \t]+\n', '\n', s)
    s = re.sub(r'\n{3,}', '\n\n', s)
    return s.strip()


def fix_visual_rtl_line(line: str) -> str:
    """pdfplumber returns Hebrew/Arabic text layers in visual (reversed) order. Reverse RTL runs per line.

    Heuristic: if the line is mostly RTL letters, reverse the whole line, then re-reverse embedded
    LTR runs (numbers / Latin words) so they read left-to-right again.
    """
    letters = [c for c in line if c.isalpha()]
    if not letters:
        return line
    rtl = sum(1 for c in letters if _HEB_ARA.match(c))
    if rtl / len(letters) < 0.5:
        return line
    rev = line[::-1]
    return re.sub(r'[A-Za-z0-9][A-Za-z0-9.,:/@%+\-_]*[A-Za-z0-9%]|[A-Za-z0-9]', lambda m: m.group(0)[::-1], rev)


def looks_visual_order(text: str) -> bool:
    """Detect reversed Hebrew text layers: common final-letter forms (ם ן ץ ף ך) appear word-initially."""
    words = re.findall(r'[\u05D0-\u05EA]{2,}', text)
    if len(words) < 3:
        return False
    finals = set('םןץףך')
    start_final = sum(1 for w in words if w[0] in finals)
    end_final = sum(1 for w in words if w[-1] in finals)
    return start_final > end_final


def table_to_markdown(rows: list[list[Any]]) -> str:
    rows = [[('' if c is None else str(c)).replace('\n', ' ').replace('|', '\\|').strip() for c in r] for r in rows if r]
    if not rows:
        return ''
    width = max(len(r) for r in rows)
    rows = [r + [''] * (width - len(r)) for r in rows]
    out = ['| ' + ' | '.join(rows[0]) + ' |', '|' + '---|' * width]
    out += ['| ' + ' | '.join(r) + ' |' for r in rows[1:]]
    return '\n'.join(out)


# ------------------------------------------------------------------ OCR

class OcrTimeout(Exception):
    pass


def _limit_pixels(img: Image.Image, max_pixels: int | None) -> Image.Image:
    if max_pixels and img.width * img.height > max_pixels:
        f = (max_pixels / (img.width * img.height)) ** 0.5
        img = img.resize((max(1, int(img.width * f)), max(1, int(img.height * f))), Image.LANCZOS)
    return img


def ocr_image(img: Image.Image, langs: tuple[str, ...], timeout: float | None = None,
              max_pixels: int | None = None) -> tuple[str, float | None]:
    img = ImageOps.exif_transpose(img)
    if img.mode not in ('L', 'RGB'):
        img = img.convert('RGB')
    img = _limit_pixels(img, max_pixels).convert('L')  # grayscale: smaller temp file, same accuracy
    lang = '+'.join(langs)
    try:
        data = pytesseract.image_to_data(img, lang=lang, config='--psm 3', output_type=pytesseract.Output.DICT,
                                         timeout=timeout or 0)
    except RuntimeError as e:  # pytesseract kills tesseract and raises RuntimeError on timeout
        if 'timeout' in str(e).lower():
            raise OcrTimeout() from e
        raise
    # Rebuild text from a single Tesseract pass: group words by (block, paragraph, line).
    lines: dict[tuple[int, int, int], list[str]] = {}
    confs: list[float] = []
    last_block = None
    order: list[tuple[int, int, int]] = []
    for i, word in enumerate(data['text']):
        if not word.strip():
            continue
        key = (data['block_num'][i], data['par_num'][i], data['line_num'][i])
        if key not in lines:
            lines[key] = []
            order.append(key)
        lines[key].append(word)
        c = float(data['conf'][i])
        if c >= 0:
            confs.append(c)
    out = []
    for key in order:
        if last_block is not None and key[:2] != last_block:
            out.append('')
        out.append(' '.join(lines[key]))
        last_block = key[:2]
    return clean_text('\n'.join(out)), (round(sum(confs) / len(confs), 1) if confs else None)


@lru_cache(maxsize=1)
def _languages() -> frozenset[str]:
    return frozenset(pytesseract.get_languages(config=''))


def available_languages() -> set[str]:
    try:
        return set(_languages())
    except Exception:  # noqa: BLE001
        return set()


# ------------------------------------------------------------------ main extraction (generator of pages)

def _remaining(opts: ExtractOptions) -> float | None:
    return None if opts.deadline is None else opts.deadline - time.monotonic()


def _budget_page(i: int) -> dict[str, Any]:
    return {'page': i + 1, 'method': 'skipped', 'text': '', 'tables': [], 'ocrConfidence': None,
            'note': 'Not processed: time budget exceeded (partial result)'}


def _ocr_or_skip(img: Image.Image, i: int, opts: ExtractOptions) -> tuple[str, float | None] | None:
    """OCR within the remaining time budget; None when the budget is (or becomes) exhausted."""
    rem = _remaining(opts)
    if rem is not None and rem < 1.0:
        opts.state['timeBudgetExceeded'] = True
        return None
    try:
        return ocr_image(img, opts.languages, timeout=rem, max_pixels=opts.max_image_pixels)
    except OcrTimeout:
        opts.state['timeBudgetExceeded'] = True
        return None


def iter_pages(data: bytes, opts: ExtractOptions) -> Iterator[dict[str, Any]]:
    """Yield one dict per page: {page, method: text|ocr, text, tables, ocrConfidence}."""
    kind = detect_kind(data)
    if kind == 'image':
        img = Image.open(io.BytesIO(data))
        n = getattr(img, 'n_frames', 1)
        for i in range(min(n, opts.max_pages)):
            img.seek(i)
            if opts.mode == 'text':
                yield {'page': i + 1, 'method': 'skipped', 'text': '', 'tables': [], 'ocrConfidence': None,
                       'note': 'Image has no text layer; OCR disabled by mode=text'}
                continue
            res = _ocr_or_skip(img.copy(), i, opts)
            if res is None:
                yield _budget_page(i)
                continue
            text, conf = res
            yield {'page': i + 1, 'method': 'ocr', 'text': text, 'tables': [], 'ocrConfidence': conf}
        return

    try:
        pdf = pdfplumber.open(io.BytesIO(data))
    except Exception as e:  # noqa: BLE001
        raise DocumentError(f'Cannot open PDF: {type(e).__name__}') from e
    rendered = None
    try:
        for i, page in enumerate(pdf.pages[: opts.max_pages]):
            text = ''
            tables: list[list[list[str]]] = []
            rem = _remaining(opts)
            if rem is not None and rem <= 0:
                opts.state['timeBudgetExceeded'] = True
                yield _budget_page(i)
                continue
            if opts.mode != 'ocr':
                text = clean_text(page.extract_text() or '')
                if looks_visual_order(text):
                    text = '\n'.join(fix_visual_rtl_line(l) for l in text.split('\n'))
                if opts.extract_tables and len(text) >= MIN_TEXT_CHARS:
                    try:
                        tables = [t for t in page.extract_tables() if t and len(t) > 1]
                    except Exception:  # noqa: BLE001
                        tables = []
            # Fast path: a short text layer on a page without images is the whole page (e.g. a one-line PDF);
            # OCR only pages with (almost) no text that contain images, i.e. scans.
            has_images = bool(getattr(page, 'images', None))
            needs_ocr = opts.mode == 'ocr' or (opts.mode == 'auto' and len(text) < MIN_TEXT_CHARS
                                               and (not text.strip() or has_images))
            if needs_ocr:
                if rendered is None:
                    rendered = pdfium.PdfDocument(data)
                bitmap = rendered[i].render(scale=opts.dpi / 72)
                img = bitmap.to_pil()
                res = _ocr_or_skip(img, i, opts)
                if res is None:
                    if text:
                        yield {'page': i + 1, 'method': 'text', 'text': text, 'tables': tables, 'ocrConfidence': None,
                               'note': 'OCR skipped: time budget exceeded; text layer only'}
                    else:
                        yield _budget_page(i)
                    continue
                ocr_text, conf = res
                if opts.mode == 'auto' and text and len(ocr_text.strip()) <= len(text.strip()) + 10:
                    # Short page whose text layer already holds everything OCR found: bill/return as text.
                    yield {'page': i + 1, 'method': 'text', 'text': text, 'tables': tables, 'ocrConfidence': None}
                else:
                    yield {'page': i + 1, 'method': 'ocr', 'text': ocr_text, 'tables': [], 'ocrConfidence': conf}
            else:
                yield {'page': i + 1, 'method': 'text', 'text': text, 'tables': tables, 'ocrConfidence': None}
    finally:
        pdf.close()
        if rendered is not None:
            rendered.close()


def page_count(data: bytes) -> int:
    if detect_kind(data) == 'pdf':
        doc = pdfium.PdfDocument(data)
        try:
            return len(doc)
        finally:
            doc.close()
    return getattr(Image.open(io.BytesIO(data)), 'n_frames', 1)


def to_markdown(pages: list[dict[str, Any]]) -> str:
    parts = []
    for p in pages:
        parts.append(f'<!-- page {p["page"]} ({p["method"]}) -->')
        if p['text']:
            parts.append(p['text'])
        for t in p.get('tables') or []:
            parts.append(table_to_markdown(t))
    return '\n\n'.join(parts).strip()
