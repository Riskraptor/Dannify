"""Fixes every installed copy takes without an update (see Backend/dannify/live.py).

    python packaging/live_details.py
        What copies are told now (config/live.json), and whether its signature
        is good.

    python packaging/live_details.py [--clients FILE | --no-clients]
                                     [--emergency VERSION [--from VERSION] --note TEXT | --no-emergency]
                                     [--notice ID --notice-text TEXT [--days N] | --no-notice]
        Change it. The version goes up by one, the file is signed with the
        release key (DANNIFY_RELEASE_KEY, or ~/.dannify/release-signing.key)
        and checked exactly as the app checks it. Then commit config/live.json
        and its .dsig to main (a pull request); copies take them within three
        hours, or at their next start.

What each does:
    --clients FILE      The identities YouTube is asked with, as innertube.py
                        reads clients.json (an "_order" list sets the order).
                        Songs that stopped playing everywhere at once are put
                        right everywhere at once.
    --emergency 4.15.0.1 --from 4.15.0 --note "Songs play again"
                        A fix build copies from 4.15.0 up to it should take now:
                        they say so plainly and fetch it straight away. The
                        build itself is published like any release, tagged
                        v4.15.0.1, and shown as "4.15.0 · fix 1".
    --notice outage-1 --notice-text "YouTube is down; saved music plays" --days 2
                        A line everyone sees once.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'Backend'))
sys.path.insert(0, str(ROOT / 'packaging'))

import release_key  # noqa: E402
from dannify import live, signing  # noqa: E402

FILE = ROOT / 'config' / 'live.json'


def read() -> dict:
    return json.loads(FILE.read_text(encoding='utf-8')) if FILE.is_file() else {'version': 0}


def describe(found: dict) -> str:
    clients = found.get('clients') or {}
    em = found.get('emergency') or {}
    notice = found.get('notice') or {}
    lines = [f"  version    {found.get('version')}"]
    names = [k for k in clients if not str(k).startswith('_')]
    lines.append(f"  clients    {', '.join(names) if names else '(the ones built in)'}")
    if em:
        lines.append(f"  emergency  {em.get('version')} for copies from {em.get('from') or '(any older)'}: "
                     f"{(em.get('notes') or {}).get('en', '') if isinstance(em.get('notes'), dict) else em.get('notes')}")
    else:
        lines.append('  emergency  (none)')
    if notice:
        until = notice.get('until')
        when = time.strftime('%Y-%m-%d %H:%M', time.localtime(until)) if until else 'no end'
        lines.append(f"  notice     {notice.get('id')}: {(notice.get('text') or {}).get('en', '')} (until {when})")
    else:
        lines.append('  notice     (none)')
    return '\n'.join(lines)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--clients')
    ap.add_argument('--no-clients', action='store_true')
    ap.add_argument('--emergency')
    ap.add_argument('--from', dest='from_version')
    ap.add_argument('--note')
    ap.add_argument('--no-emergency', action='store_true')
    ap.add_argument('--notice')
    ap.add_argument('--notice-text')
    ap.add_argument('--days', type=float, default=0)
    ap.add_argument('--no-notice', action='store_true')
    args = ap.parse_args(argv)

    details = read()
    sig_path = FILE.with_name(FILE.name + signing.SIGNATURE_SUFFIX)
    changing = any([args.clients, args.no_clients, args.emergency, args.no_emergency, args.notice, args.no_notice])
    if not changing:
        if not FILE.is_file():
            print(f'No {FILE.name} yet: copies use what is built into them.')
            return 0
        found = live.accept(FILE.read_bytes(), sig_path.read_text(encoding='ascii') if sig_path.is_file() else '',
                            release_key._shipped_public_key())
        if not found:
            print(f'{FILE.name} is NOT accepted by the app (unsigned, or changed since it was signed).')
            return 1
        print(f'What every copy is told ({FILE.relative_to(ROOT)}):')
        print(describe(found))
        return 0

    if args.clients:
        details['clients'] = json.loads(Path(args.clients).read_text(encoding='utf-8'))
    if args.no_clients:
        details.pop('clients', None)
    if args.emergency:
        if not args.note:
            raise SystemExit('an emergency fix needs --note: what it puts right, in a few words')
        details['emergency'] = {
            'version': args.emergency.lstrip('vV'),
            'from': (args.from_version or '').lstrip('vV'),
            'notes': {'en': args.note},
        }
    if args.no_emergency:
        details.pop('emergency', None)
    if args.notice:
        if not args.notice_text:
            raise SystemExit('a notice needs --notice-text')
        details['notice'] = {'id': args.notice, 'text': {'en': args.notice_text}}
        if args.days:
            details['notice']['until'] = int(time.time() + args.days * 86400)
    if args.no_notice:
        details.pop('notice', None)
    details['version'] = int(details.get('version') or 0) + 1

    raw = (json.dumps(details, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
    secret = release_key.load_secret()
    if signing.public_key(secret).hex() != release_key._shipped_public_key():
        raise SystemExit('this key is not the one installed copies trust (PUBLIC_KEY in updates.py)')
    FILE.parent.mkdir(parents=True, exist_ok=True)
    FILE.write_bytes(raw)
    release_key.sign_file('live', str(details['version']), FILE, secret)
    found = live.accept(FILE.read_bytes(), sig_path.read_text(encoding='ascii'), release_key._shipped_public_key())
    if not found:
        raise SystemExit('signed, but the app would not accept it: nothing to commit')
    print('Signed. What every copy will be told:')
    print(describe(found))
    print(f'\nNow commit {FILE.relative_to(ROOT)} and its .dsig to main.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
