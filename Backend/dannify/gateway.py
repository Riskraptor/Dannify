"""What every request passes through: compression for text (never for
media), the session gate that keeps the app private, and the request log."""

from __future__ import annotations

import hmac as _hmac

from loguru import logger

from . import api


def install(app) -> None:  # noqa: ANN001
    # Search and home payloads run to tens of KB of JSON. Compressing them
    # costs a millisecond and pays for itself on every phone on the LAN.
    #
    # Audio must be left alone, and the size floor does not do that. The floor
    # only applies to a response that arrives in one piece; a streamed one goes
    # down the other branch and is compressed whatever its size, which drops
    # Content-Length and switches to chunked. A track then has no length for
    # the player to read, so the bar sits at 0:00 forever, and a range reply is
    # worse than that: Content-Range still describes the bytes that were asked
    # for while the body is a gzip stream of them. A thousand-byte range came
    # back as 504 bytes with a header promising 1024.
    from fastapi.middleware.gzip import GZipMiddleware

    _NEVER_GZIP = ('/downloads/', '/opened/', '/cover', '/api/stream')

    class _GzipTextOnly:
        """Compression for the JSON and the interface, never for media."""

        def __init__(self, inner):
            self.inner = inner
            self.gzip = GZipMiddleware(inner, minimum_size=2048, compresslevel=5)

        async def __call__(self, scope, receive, send):
            if scope['type'] == 'http' and not scope['path'].startswith(_NEVER_GZIP):
                await self.gzip(scope, receive, send)
                return
            await self.inner(scope, receive, send)

    app.add_middleware(_GzipTextOnly)

    # --- Private by default -------------------------------------------------
    # Dannify is a desktop app that happens to talk to itself over HTTP. The
    # window arrives carrying a one-shot key and trades it for a cookie;
    # everything else (another browser, another program, a curious phone)
    # gets a flat 404. Without this the whole library and API answer anyone
    # who opens localhost.
    # --- One ASGI pass: private by default, plus request logging ----------
    #
    # This used to be two @app.middleware('http') functions. Starlette wraps
    # those in a task group and a memory stream, which streaming cannot
    # survive: an <audio> element aborts and re-issues range requests
    # constantly, and each abort surfaced as "RuntimeError: No response
    # returned" and killed playback. Pure ASGI has no wrapper, so aborts are
    # just aborts, and every request gets a little faster too.
    #
    # The gate itself: the app window arrives carrying a one-shot key and
    # trades it for a cookie. Anything else, another browser, another
    # program, a curious phone, is answered as if nothing is listening.
    import time as _time

    _COOKIE = 'dnf_session'
    # Nothing is reachable without the session key, including the readiness
    # probe: an open endpoint is an open door, and it told anyone who knocked
    # what was behind it. The shell sends the key like any other caller.
    _OPEN_PATHS: set[str] = set()
    _QUIET_PREFIXES = ('/assets/', '/cover', '/favicon', '/downloads/')
    _QUIET_EXACT = {'/list', '/api/queue', '/api/version', '/api/settings', '/api/net'}

    class _Gateway:
        def __init__(self, inner):
            self.inner = inner

        @staticmethod
        def _presented(scope) -> tuple[str, bool]:
            """The key this request carries, and whether it came in the URL."""
            from urllib.parse import parse_qs

            query = parse_qs(scope.get('query_string', b'').decode('latin-1'))
            in_url = (query.get('k') or [''])[0]
            if in_url:
                return in_url, True
            for name, value in scope.get('headers') or ():
                if name == b'x-dannify-key':
                    return value.decode('latin-1'), False
                if name == b'cookie':
                    for part in value.decode('latin-1').split(';'):
                        key, _, val = part.strip().partition('=')
                        if key == _COOKIE:
                            return val, False
            return '', False

        async def __call__(self, scope, receive, send):
            if scope['type'] not in ('http', 'websocket'):
                await self.inner(scope, receive, send)
                return

            token = api.state.auth_token
            path = scope.get('path', '')
            if token:
                given, from_url = self._presented(scope)
                if not _hmac.compare_digest(given.encode(), token.encode()) and (
                    path not in _OPEN_PATHS
                ):
                    await _refuse(scope, send)
                    return
            else:
                # Development: no shell, no key. Still only for a page that
                # thinks it is talking to this machine. A web page that points
                # its own domain name at 127.0.0.1 (DNS rebinding) arrives with
                # that name in Host, and is turned away.
                from_url = False
                if not _loopback_host(scope):
                    await _refuse(scope, send)
                    return

            if scope['type'] == 'websocket':
                await self.inner(scope, receive, send)
                return

            started = _time.perf_counter()
            quiet = path.startswith(_QUIET_PREFIXES) or path in _QUIET_EXACT

            async def send_wrapper(message):
                if message['type'] == 'http.response.start':
                    if from_url:
                        # Hand the window a cookie so every later asset,
                        # audio range request and websocket carries the key.
                        message.setdefault('headers', [])
                        message['headers'].append((
                            b'set-cookie',
                            f'{_COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax'.encode(),
                        ))
                    if not quiet:
                        _log_response(scope, message['status'], started)
                await send(message)

            await self.inner(scope, receive, send_wrapper)

    def _loopback_host(scope) -> bool:
        for name, value in scope.get('headers') or ():
            if name == b'host':
                host = value.decode('latin-1').strip().lower()
                if host.startswith('['):
                    host = host[1:].split(']', 1)[0]
                else:
                    host = host.rsplit(':', 1)[0] if host.count(':') == 1 else host
                return host in ('127.0.0.1', 'localhost', '::1')
        return False

    async def _refuse(scope, send) -> None:
        if scope['type'] == 'websocket':
            await send({'type': 'websocket.close', 'code': 1008})
            return
        await send({
            'type': 'http.response.start',
            'status': 404,
            'headers': [(b'content-length', b'0')],
        })
        await send({'type': 'http.response.body', 'body': b''})

    def _log_response(scope, status: int, started: float) -> None:
        # Time to first byte, which for a stream is the number that matters.
        ms = (_time.perf_counter() - started) * 1000
        raw = scope.get('query_string', b'').decode('latin-1')
        # Never echo the session key into the log file.
        q = ''
        if raw:
            q = '?' + '&'.join(p for p in raw.split('&') if not p.startswith('k='))
        tag = '✗' if status >= 500 else ('⚠' if status >= 400 else '→')
        lvl = 'ERROR' if status >= 500 else ('WARNING' if status >= 400 else 'INFO')
        logger.bind(component='http').log(
            lvl,
            '{} {} {}{}  {}  {:.0f}ms',
            tag,
            scope.get('method', '?'),
            scope.get('path', ''),
            q[:80],
            status,
            ms,
        )

    app.add_middleware(_Gateway)
