"""Dannify's problem-report server.

Receives the reports the app sends (Backend/dannify/report.py), keeps each one
on disk, and lets the developer read them. Nothing else: no accounts, no
database to run, one process.

    POST /reports                 multipart: id, version, category, description,
                                  contact, and optionally a zip "diagnostics"
    GET  /admin                   a page listing reports (asks for the token)
    GET  /api/reports             the list, newest first        (token)
    GET  /api/reports/{id}        one report                    (token)
    GET  /api/reports/{id}/zip    its diagnostics               (token)
    DELETE /api/reports/{id}      remove one                    (token)
    GET  /health                  for the host's health check

Settings, from the environment:

    REPORT_ADMIN_TOKEN    required: the token for everything under /api and /admin
    REPORT_DATA_DIR       where reports are kept (default ./data)
    REPORT_NOTIFY_URL     optional: a Discord or Slack webhook told of each new report
    REPORT_MAX_PER_HOUR   reports one address may send in an hour (default 20)
"""

from __future__ import annotations

import hmac
import json
import os
import re
import shutil
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

DATA = Path(os.getenv('REPORT_DATA_DIR', 'data')).resolve()
TOKEN = os.getenv('REPORT_ADMIN_TOKEN', '')
NOTIFY = os.getenv('REPORT_NOTIFY_URL', '')
PER_HOUR = int(os.getenv('REPORT_MAX_PER_HOUR', '20'))

MAX_ZIP = 8 * 1024 * 1024
MAX_TEXT = 5000
CATEGORIES = {'playback', 'downloads', 'lyrics', 'looks', 'crash', 'other'}
_ID = re.compile(r'^[A-Z0-9]{6,16}$')
_VERSION = re.compile(r'^[0-9][0-9A-Za-z.\-+]{0,30}$')

app = FastAPI(title='Dannify reports', docs_url=None, redoc_url=None, openapi_url=None)

_recent: dict[str, deque] = defaultdict(deque)
_lock = threading.Lock()


def _allowed(address: str) -> bool:
    now = time.time()
    with _lock:
        seen = _recent[address]
        while seen and now - seen[0] > 3600:
            seen.popleft()
        if len(seen) >= PER_HOUR:
            return False
        seen.append(now)
        return True


def _require(token: Optional[str]) -> None:
    given = (token or '').removeprefix('Bearer ').strip()
    if not TOKEN or not hmac.compare_digest(given.encode(), TOKEN.encode()):
        raise HTTPException(status_code=401, detail='token required')


def _folder(rid: str) -> Path:
    name = _rid_dirname(rid)
    for day in sorted(DATA.glob('*'), reverse=True):
        candidate = day / name
        if candidate.is_dir():
            return candidate
    raise HTTPException(status_code=404, detail='no such report')


def _rid_dirname(rid: str) -> str:
    if not _ID.match(rid):
        raise HTTPException(status_code=404, detail='no such report')
    # Canonical numeric form for storage paths: no path separators, no dots.
    return f'{int(rid, 36):025d}'


def _notify(meta: dict[str, Any]) -> None:
    if not NOTIFY:
        return
    import urllib.request

    text = (f"New Dannify report {meta['id']} ({meta['category']}, v{meta['version']}): "
            f"{meta['description'][:300]}")
    body = json.dumps({'content': text, 'text': text}).encode()
    try:
        urllib.request.urlopen(
            urllib.request.Request(NOTIFY, data=body, headers={'Content-Type': 'application/json'}),
            timeout=10,
        )
    except Exception:
        pass


@app.get('/health')
def health() -> dict[str, bool]:
    return {'ok': True}


@app.post('/reports', status_code=201)
async def receive(
    request: Request,
    id: str = Form(...),
    version: str = Form(''),
    category: str = Form('other'),
    description: str = Form(...),
    contact: str = Form(''),
    diagnostics: Optional[UploadFile] = File(None),
) -> dict[str, Any]:
    address = request.client.host if request.client else '?'
    if not _allowed(address):
        raise HTTPException(status_code=429, detail='too many reports; try later')
    rid = id.strip().upper()
    if not _ID.match(rid):
        raise HTTPException(status_code=400, detail='bad id')
    text = description.strip()
    if not 10 <= len(text) <= MAX_TEXT:
        raise HTTPException(status_code=400, detail='description must be 10 to 5000 characters')
    meta = {
        'id': rid,
        'version': version.strip() if _VERSION.match(version.strip()) else '',
        'category': category if category in CATEGORIES else 'other',
        'description': text,
        'contact': contact.strip()[:200],
        'received': time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime()) + ' UTC',
        'diagnostics': False,
    }
    day = DATA / time.strftime('%Y-%m-%d', time.gmtime())
    folder = day / _rid_dirname(rid)
    try:
        folder.mkdir(parents=True)
    except FileExistsError:
        # The app retries a report it could not confirm; the first one counts.
        return {'id': rid, 'status': 'already received'}
    if diagnostics is not None:
        data = await diagnostics.read(MAX_ZIP + 1)
        if len(data) > MAX_ZIP:
            shutil.rmtree(folder, ignore_errors=True)
            raise HTTPException(status_code=413, detail='diagnostics too large')
        if data[:2] != b'PK':
            shutil.rmtree(folder, ignore_errors=True)
            raise HTTPException(status_code=400, detail='diagnostics must be a zip')
        (folder / 'diagnostics.zip').write_bytes(data)
        meta['diagnostics'] = True
    (folder / 'report.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    threading.Thread(target=_notify, args=(meta,), daemon=True).start()
    return {'id': rid, 'status': 'received'}


@app.get('/api/reports')
def list_reports(authorization: Optional[str] = Header(None), limit: int = 200) -> JSONResponse:
    _require(authorization)
    out = []
    for meta in sorted(DATA.glob('*/*/report.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        try:
            out.append(json.loads(meta.read_text(encoding='utf-8')))
        except (OSError, ValueError):
            continue
    return JSONResponse(out)


@app.get('/api/reports/{rid}')
def one_report(rid: str, authorization: Optional[str] = Header(None)) -> JSONResponse:
    _require(authorization)
    return JSONResponse(json.loads((_folder(rid) / 'report.json').read_text(encoding='utf-8')))


@app.get('/api/reports/{rid}/zip')
def report_zip(rid: str, authorization: Optional[str] = Header(None)) -> FileResponse:
    _require(authorization)
    path = _folder(rid) / 'diagnostics.zip'
    if not path.is_file():
        raise HTTPException(status_code=404, detail='no diagnostics with this report')
    return FileResponse(path, media_type='application/zip', filename=f'dannify-{rid}.zip')


@app.delete('/api/reports/{rid}')
def delete_report(rid: str, authorization: Optional[str] = Header(None)) -> dict[str, bool]:
    _require(authorization)
    shutil.rmtree(_folder(rid), ignore_errors=True)
    return {'deleted': True}


ADMIN = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dannify reports</title><style>
body{font:14px system-ui,sans-serif;margin:0;background:#121214;color:#eee}header{padding:16px 24px;border-bottom:1px solid #2a2a2e;display:flex;gap:12px;align-items:center}
h1{font-size:18px;margin:0}main{padding:16px 24px}.r{background:#1b1b1f;border-radius:10px;padding:14px 16px;margin-bottom:10px}
.m{color:#9a9aa3;font-size:12px;margin-bottom:6px}.t{white-space:pre-wrap}button,a.b{background:#1ad05c;color:#000;border:0;border-radius:999px;padding:6px 14px;font-weight:600;cursor:pointer;text-decoration:none;font-size:12px}
.x{background:#333;color:#eee}.cat{display:inline-block;padding:1px 8px;border-radius:999px;background:#2a2a2e;margin-right:6px}
</style></head><body><header><h1>Dannify reports</h1><span id="n" class="m"></span></header><main id="list">Loading…</main>
<script>
let token = sessionStorage.getItem('t') || prompt('Admin token'); sessionStorage.setItem('t', token)
const H = { Authorization: 'Bearer ' + token }
const esc = (s) => String(s || '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c])
async function load() {
  const r = await fetch('/api/reports', { headers: H })
  if (r.status === 401) { sessionStorage.removeItem('t'); document.getElementById('list').textContent = 'Wrong token. Reload to try again.'; return }
  const list = await r.json()
  document.getElementById('n').textContent = list.length + ' reports'
  document.getElementById('list').innerHTML = list.map((x) => `<div class="r"><div class="m"><span class="cat">${esc(x.category)}</span>${esc(x.id)} · v${esc(x.version)} · ${esc(x.received)}${x.contact ? ' · ' + esc(x.contact) : ''}</div>
    <div class="t">${esc(x.description)}</div><div style="margin-top:10px;display:flex;gap:8px">
    ${x.diagnostics ? `<button onclick="dl('${esc(x.id)}')">Diagnostics</button>` : ''}<button class="x" onclick="del('${esc(x.id)}')">Delete</button></div></div>`).join('') || 'No reports yet.'
}
async function dl(id) { const r = await fetch('/api/reports/' + id + '/zip', { headers: H }); const b = await r.blob(); const a = document.createElement('a'); a.href = URL.createObjectURL(b); a.download = 'dannify-' + id + '.zip'; a.click() }
async function del(id) { if (confirm('Delete report ' + id + '?')) { await fetch('/api/reports/' + id, { method: 'DELETE', headers: H }); load() } }
load()
</script></body></html>"""


@app.get('/admin', response_class=HTMLResponse)
def admin() -> str:
    return ADMIN
