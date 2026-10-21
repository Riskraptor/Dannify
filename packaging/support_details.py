"""Dannify's payment details, as every installed copy reads them from GitHub.

    python packaging/support_details.py
        What copies are told now (config/support-live.json), and whether its
        signature is good.

    python packaging/support_details.py [--github LOGIN] [--no-github]
                                        [--paypal LINK] [--no-paypal]
                                        [--till NUMBER | --paybill NUMBER --account ACCOUNT]
                                        [--mpesa-name NAME] [--no-mpesa]
                                        [--kofi LINK] [--message TEXT]
        Change them. The version goes up by one, the file is signed with the
        release key (DANNIFY_RELEASE_KEY, or ~/.dannify/release-signing.key,
        the same one releases are signed with), and it is checked exactly as
        the app checks it. Then commit config/support-live.json and its .dsig
        to main (a pull request); copies take them within twelve hours.

Examples:
    --paypal https://www.paypal.com/ncp/payment/PLB-XXXXXXXXXXXX
    --paypal mypaypalname                       (a paypal.me name)
    --till 8496746
    --paybill 247247 --account 0712345678
    --message "Thank you for keeping Dannify free!"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'Backend'))
sys.path.insert(0, str(ROOT / 'packaging'))

import release_key  # noqa: E402
from dannify import signing, support  # noqa: E402

FILE = ROOT / 'config' / 'support-live.json'


def read() -> dict:
    return json.loads(FILE.read_text(encoding='utf-8')) if FILE.is_file() else {'version': 0}


def what_copies_show(raw: bytes, signature: str) -> dict | None:
    """The details as an installed copy would show them, or None if it would
    not accept the file."""

    found = support.accept_live(raw, signature, release_key._shipped_public_key())
    if not found:
        return None
    kept = dict(support._live)
    try:
        support._live.clear()
        support._live.update(found)
        return support.config()
    finally:
        support._live.clear()
        support._live.update(kept)


def describe(shown: dict, version: int) -> str:
    mpesa = shown.get('mpesa') or {}
    if mpesa.get('kind') == 'paybill':
        m = f"paybill {mpesa['number']}, account {mpesa.get('account') or '(none)'}"
    elif mpesa:
        m = f"till {mpesa['number']}"
    else:
        m = '(not shown)'
    if mpesa.get('name'):
        m += f" ({mpesa['name']})"
    return '\n'.join(
        [
            f'  version  {version}',
            f"  GitHub   {shown.get('sponsors_link') or '(not shown)'}",
            f"  PayPal   {shown.get('paypal_link') or '(not shown)'}",
            f'  M-PESA   {m}  (shown in Kenya only)',
            f"  Ko-fi    {shown.get('link') or '(not shown)'}",
            f"  message  {shown.get('message') or '(the built-in one)'}",
        ]
    )


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--github')
    ap.add_argument('--no-github', action='store_true')
    ap.add_argument('--paypal')
    ap.add_argument('--no-paypal', action='store_true')
    ap.add_argument('--till')
    ap.add_argument('--paybill')
    ap.add_argument('--account')
    ap.add_argument('--mpesa-name')
    ap.add_argument('--no-mpesa', action='store_true')
    ap.add_argument('--kofi')
    ap.add_argument('--message')
    args = ap.parse_args(argv)

    details = read()
    sig_path = FILE.with_name(FILE.name + signing.SIGNATURE_SUFFIX)
    changing = any(
        v not in (None, False)
        for v in (args.github, args.no_github, args.paypal, args.no_paypal, args.till, args.paybill, args.mpesa_name, args.no_mpesa, args.kofi, args.message)
    )
    if not changing:
        if not FILE.is_file():
            print(f'No {FILE.name} yet: copies use the details built into them.')
            return 0
        shown = what_copies_show(FILE.read_bytes(), sig_path.read_text(encoding='ascii') if sig_path.is_file() else '')
        if shown is None:
            print(f'{FILE.name} is NOT accepted by the app (unsigned, or changed since it was signed).')
            return 1
        print(f'What every copy is told ({FILE.relative_to(ROOT)}):')
        print(describe(shown, details.get('version', 0)))
        return 0

    if args.till and args.paybill:
        raise SystemExit('a till or a paybill, not both')
    if args.github is not None:
        details['github'] = args.github.strip()
    if args.no_github:
        details['github'] = ''
    if args.paypal is not None:
        details['paypal'] = args.paypal.strip()
    if args.no_paypal:
        details['paypal'] = ''
    if args.till or args.paybill:
        mpesa = {'kind': 'till' if args.till else 'paybill', 'number': (args.till or args.paybill).strip()}
        if args.paybill:
            mpesa['account'] = (args.account or '').strip()
        details['mpesa'] = mpesa
    if args.mpesa_name is not None:
        details.setdefault('mpesa', {})['name'] = args.mpesa_name.strip()
    if args.no_mpesa:
        details['mpesa'] = {}
    if args.kofi is not None:
        details['link'] = args.kofi.strip()
    if args.message is not None:
        details['message'] = args.message.strip()
    details['version'] = int(details.get('version') or 0) + 1

    raw = (json.dumps(details, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
    secret = release_key.load_secret()
    if signing.public_key(secret).hex() != release_key._shipped_public_key():
        raise SystemExit('this key is not the one installed copies trust (PUBLIC_KEY in updates.py)')
    FILE.parent.mkdir(parents=True, exist_ok=True)
    FILE.write_bytes(raw)
    release_key.sign_file('support', str(details['version']), FILE, secret)
    shown = what_copies_show(FILE.read_bytes(), sig_path.read_text(encoding='ascii'))
    if shown is None:
        raise SystemExit('signed, but the app would not accept it: nothing to commit')
    print('Signed. What every copy will be told:')
    print(describe(shown, details['version']))
    asked = {'paypal': args.paypal and not shown.get('paypal_link'), 'kofi': args.kofi and not shown.get('link')}
    for what, refused in asked.items():
        if refused:
            print(f'  NOTE: the {what} address given is not one the app accepts, so it will not be shown.')
    print(f'\nNow commit {FILE.relative_to(ROOT)} and its .dsig to main.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
