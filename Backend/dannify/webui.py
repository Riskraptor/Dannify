"""Serving the interface itself: the built files, packed or loose, with the
single-page app's own fallback to index.html."""

from __future__ import annotations

import mimetypes
from typing import Optional

from fastapi.staticfiles import StaticFiles


# Paths the interface never routes to. An API call that matched no route used
# to fall through to the interface and come back as index.html with a 200, so
# the caller got a web page where it expected data: the artist page for
# "AC/DC" did exactly that, and broke on it.
def _not_ui(rel: str) -> bool:
    # StaticFiles hands over an OS path: backslashes, on Windows.
    rel = rel.replace('\\', '/').lstrip('/').lower()
    return rel == 'api' or rel.startswith('api/')


class SPAStaticFiles(StaticFiles):
    """Serve ``index.html`` for unknown paths so SPA routing works."""

    async def get_response(self, path: str, scope):
        if _not_ui(path):
            from starlette.exceptions import HTTPException as _StarletteHTTP

            raise _StarletteHTTP(status_code=404)
        try:
            return await super().get_response(path, scope)
        except Exception:
            return await super().get_response('index.html', scope)


class PackedUI:
    """Serve the interface out of the shipped resource file.

    A folder of readable HTML, JavaScript and CSS in the install directory made
    the app look like a web page someone had copied into Program Files, so the
    built interface ships as one packed file instead (see dannify/respack.py).
    This is the same thing StaticFiles did, reading from that file: a path, a
    content type, an ETag, and index.html for anything the router owns.
    """

    def __init__(self, pack) -> None:
        self._pack = pack
        self._etag = f'"{pack.stamp}"'

    # A path that names a file is a file, not a route. Handing back index.html
    # with a 200 for a missing script means the browser parses HTML as
    # JavaScript and the window comes up blank with a syntax error, when a 404
    # would have said plainly that the file is not there.
    _FILEY = (
        '.js', '.mjs', '.css', '.map', '.woff', '.woff2', '.ttf', '.otf',
        '.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.ico', '.json',
        '.txt', '.wasm',
    )

    def _member(self, path: str) -> Optional[str]:
        rel = path.lstrip('/')
        if _not_ui(rel):
            return None
        if not rel or rel.endswith('/'):
            rel += 'index.html'
        name = f'ui/{rel}'
        if name in self._pack:
            return name
        if rel.lower().endswith(self._FILEY):
            return None
        # Anything else is a route the front end handles itself.
        return 'ui/index.html'

    async def __call__(self, scope, receive, send) -> None:
        from starlette.responses import PlainTextResponse, Response

        if scope['type'] != 'http':
            return
        if scope['method'] not in ('GET', 'HEAD'):
            await PlainTextResponse('Method Not Allowed', status_code=405)(
                scope, receive, send,
            )
            return

        name = self._member(scope['path'])
        if name is None:
            await PlainTextResponse('Not Found', status_code=404)(
                scope, receive, send,
            )
            return
        body = self._pack.read(name)
        media = mimetypes.guess_type(name)[0] or 'application/octet-stream'

        # Vite puts a content hash in every asset filename, so those can be
        # cached for good. index.html is the one file whose name stays the
        # same across builds, and it names the others.
        if name == 'ui/index.html':
            cache = 'no-cache'
        else:
            cache = 'public, max-age=31536000, immutable'

        headers = {'Cache-Control': cache, 'ETag': self._etag}
        asked = b''
        for key, value in scope.get('headers', ()):
            if key.lower() == b'if-none-match':
                asked = value
                break
        if self._etag.encode() in (t.strip() for t in asked.split(b',')):
            await Response(status_code=304, headers=headers)(scope, receive, send)
            return

        await Response(
            content=b'' if scope['method'] == 'HEAD' else body,
            media_type=media,
            headers={**headers, 'Content-Length': str(len(body))},
        )(scope, receive, send)


def _fix_mime_types() -> None:
    mimetypes.add_type('application/javascript', '.js')
    mimetypes.add_type('application/javascript', '.mjs')
    mimetypes.add_type('text/css', '.css')
