"""Donations / "support the app": wired for Paystack, config-only.

Nothing here contains secrets. Drop your details in ONE of these places and
the Support screen lights up:

* environment variables: ``DANNIFY_PAYSTACK_PUBLIC_KEY``,
  ``DANNIFY_DONATE_LINK``, ``DANNIFY_DONATE_CURRENCY``,
  ``DANNIFY_DONATE_AMOUNTS`` (comma separated), ``DANNIFY_DONATE_MESSAGE``;
* or ``support.json`` next to the app's settings (the data folder), with the
  same keys in snake_case.

Two flows are supported, in this order:

1. ``payment_link``: a Paystack Payment Page URL. Opened in the browser.
   Zero code, no keys in the app.
2. ``public_key``: Paystack Inline: the app opens its own checkout page
   (``/support/checkout``) which loads Paystack's script and runs the
   transaction. Only the PUBLIC key is ever used client-side.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from loguru import logger

_DEFAULTS: dict[str, Any] = {
    'enabled': True,
    'provider': 'paystack',
    'public_key': '',
    'payment_link': '',
    'currency': 'KES',
    'amounts': [200, 500, 1000, 2000],
    'message': '',
    'email': '',
}

_config: dict[str, Any] = dict(_DEFAULTS)
_path: Path | None = None


def config_paths(data_dir: Path, name: str) -> list[Path]:
    """Where a drop-in config file may live, lowest precedence first.

    ``<install dir>/config/<name>`` lets whoever packages the build ship
    settings for every user; ``<data dir>/<name>`` is the per-user override.
    """

    import sys

    paths: list[Path] = []
    if getattr(sys, 'frozen', False):
        paths.append(Path(sys.executable).parent / 'config' / name)
    else:
        paths.append(Path(__file__).resolve().parents[2] / 'packaging' / 'config' / name)
    paths.append(Path(data_dir) / name)
    return paths


def init(data_dir: Path) -> None:
    global _path
    _path = Path(data_dir) / 'support.json'
    config = dict(_DEFAULTS)
    # Later files win: the packager ships defaults next to the exe, the user's
    # own data folder can override them, and environment variables beat both.
    for path in config_paths(data_dir, 'support.json'):
        try:
            stored = json.loads(path.read_text(encoding='utf-8'))
            if isinstance(stored, dict):
                config.update({k: v for k, v in stored.items() if k in _DEFAULTS})
        except FileNotFoundError:
            continue
        except Exception:
            logger.opt(exception=True).debug('Could not read {}', path)

    env_map = {
        'public_key': 'DANNIFY_PAYSTACK_PUBLIC_KEY',
        'payment_link': 'DANNIFY_DONATE_LINK',
        'currency': 'DANNIFY_DONATE_CURRENCY',
        'message': 'DANNIFY_DONATE_MESSAGE',
        'email': 'DANNIFY_DONATE_EMAIL',
    }
    for key, env in env_map.items():
        value = os.getenv(env, '').strip()
        if value:
            config[key] = value
    amounts = os.getenv('DANNIFY_DONATE_AMOUNTS', '').strip()
    if amounts:
        parsed = [int(a) for a in amounts.replace(' ', '').split(',') if a.isdigit()]
        if parsed:
            config['amounts'] = parsed
    disabled = os.getenv('DANNIFY_DONATE_DISABLED', '').strip().lower()
    if disabled in ('1', 'true', 'yes'):
        config['enabled'] = False

    _config.clear()
    _config.update(config)
    if configured():
        logger.info('Support/donations configured ({})', _config['provider'])


def configured() -> bool:
    return bool(
        _config.get('enabled')
        and (_config.get('payment_link') or _config.get('public_key'))
    )


def config() -> dict[str, Any]:
    """Public config for the UI (no secret keys exist in this app)."""

    return {
        'enabled': bool(_config.get('enabled')),
        'configured': configured(),
        'provider': _config.get('provider', 'paystack'),
        'public_key': _config.get('public_key', ''),
        'payment_link': _config.get('payment_link', ''),
        'currency': _config.get('currency', 'KES'),
        'amounts': list(_config.get('amounts') or []),
        'message': _config.get('message', ''),
        'email': _config.get('email', ''),
    }


CHECKOUT_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Support Dannify</title>
<style>
  :root{color-scheme:dark}
  body{margin:0;height:100vh;display:grid;place-items:center;background:#0e0e11;
    color:#f0f0f3;font-family:'Segoe UI Variable Text','Segoe UI',system-ui,sans-serif}
  .card{width:min(420px,92vw);text-align:center;padding:32px 24px}
  h1{font-size:22px;margin:0 0 6px}
  p{color:#a9a9b4;font-size:13.5px;line-height:1.5;margin:0 0 20px}
  .spin{width:28px;height:28px;border:3px solid rgba(255,255,255,.18);
    border-right-color:#1ad05c;border-radius:50%;margin:0 auto 18px;
    animation:s .8s linear infinite}
  @keyframes s{to{transform:rotate(360deg)}}
  .ok{color:#1ad05c;font-size:40px;line-height:1}
  button{margin-top:18px;padding:9px 18px;border:0;border-radius:6px;
    background:#1ad05c;color:#03160a;font-weight:600;font-size:13px}
</style></head>
<body><div class="card" id="root">
  <div class="spin"></div>
  <h1>Opening secure checkout…</h1>
  <p>Payment is handled by Paystack. Dannify never sees your card details.</p>
</div>
<script src="https://js.paystack.co/v2/inline.js"></script>
<script>
  const q = new URLSearchParams(location.search);
  const root = document.getElementById('root');
  function done(icon, title, text) {
    root.innerHTML = '<div class="ok">' + icon + '</div><h1>' + title +
      '</h1><p>' + text + '</p><button onclick="window.close()">Close</button>';
  }
  try {
    const popup = new PaystackPop();
    popup.newTransaction({
      key: q.get('key'),
      email: q.get('email') || 'supporter@dannify.app',
      amount: Math.round(parseFloat(q.get('amount') || '0') * 100),
      currency: q.get('currency') || 'KES',
      metadata: { custom_fields: [{ display_name: 'Source', variable_name: 'source',
        value: 'Dannify desktop' }] },
      onSuccess: () => done('&#10003;', 'Thank you!',
        'Your support keeps Dannify free and getting better.'),
      onCancel: () => done('&#8212;', 'Payment cancelled',
        'No charge was made. You can close this window.'),
    });
  } catch (e) {
    done('!', 'Could not start checkout', String(e));
  }
</script></body></html>"""
