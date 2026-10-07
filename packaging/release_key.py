"""Dannify's release signing key: make it once, sign with it every release.

    python packaging/release_key.py new            make the key (once, ever)
    python packaging/release_key.py public         print the public half
    python packaging/release_key.py sign <kind> <version> <file>
                                                   write <file>.sig
    python packaging/release_key.py verify <kind> <version> <file>

The private key is read from the DANNIFY_RELEASE_KEY environment variable
(64 hex characters; that is how a CI secret hands it over) or else from
%USERPROFILE%\\.dannify\\release-signing.key. It is never written inside the
repository. Lose it and installed copies can no longer be updated except by
installing by hand; leak it and anyone can sign an update. Keep a backup
somewhere offline.

The public half goes into Backend/dannify/updates.py as PUBLIC_KEY, which is
what every installed copy checks releases against.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'Backend'))

from dannify import signing  # noqa: E402

KEY_FILE = Path.home() / '.dannify' / 'release-signing.key'
KINDS = ('package', 'installer')


def load_secret() -> bytes:
    raw = os.getenv('DANNIFY_RELEASE_KEY', '').strip()
    source = 'DANNIFY_RELEASE_KEY'
    if not raw:
        if not KEY_FILE.is_file():
            raise SystemExit(
                f'no release key: set DANNIFY_RELEASE_KEY or run "release_key.py new" ({KEY_FILE})'
            )
        raw = KEY_FILE.read_text(encoding='ascii').strip()
        source = str(KEY_FILE)
    try:
        secret = bytes.fromhex(raw)
    except ValueError:
        raise SystemExit(f'the release key in {source} is not hex') from None
    if len(secret) != 32:
        raise SystemExit(f'the release key in {source} is not 32 bytes')
    return secret


def sign_file(kind: str, version: str, path: Path, secret: bytes) -> Path:
    if kind not in KINDS:
        raise SystemExit(f'kind must be one of {KINDS}')
    digest = signing.sha256_file(path)
    signature = signing.sign(secret, signing.statement(kind, version, digest))
    # Checked straight back against the public half before anything is
    # written: a signature that does not verify must never be published.
    if not signing.verify(signing.public_key(secret), signing.statement(kind, version, digest), signature):
        raise SystemExit('the signature did not verify; nothing written')
    out = path.with_name(path.name + '.sig')
    out.write_text(signature.hex() + '\n', encoding='ascii')
    return out


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    command = argv[0]
    if command == 'new':
        if KEY_FILE.exists():
            raise SystemExit(f'{KEY_FILE} already exists; refusing to replace a release key')
        KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        secret = os.urandom(32)
        KEY_FILE.write_text(secret.hex() + '\n', encoding='ascii')
        print(f'Release key written to {KEY_FILE}. Back it up somewhere offline.')
        print(f'PUBLIC_KEY = {signing.public_key(secret).hex()!r}')
        return 0
    if command == 'public':
        print(signing.public_key(load_secret()).hex())
        return 0
    if command in ('sign', 'verify') and len(argv) == 4:
        kind, version, path = argv[1], argv[2], Path(argv[3])
        if not path.is_file():
            raise SystemExit(f'no such file: {path}')
        if command == 'sign':
            print(f'  signed {path.name} -> {sign_file(kind, version, path, load_secret()).name}')
            return 0
        sig = path.with_name(path.name + '.sig')
        public = os.getenv('DANNIFY_RELEASE_PUBLIC', '').strip() or signing.public_key(load_secret()).hex()
        ok = sig.is_file() and signing.verify_release(
            public, kind, version, signing.sha256_file(path), sig.read_text(encoding='ascii')
        )
        print(f'  {path.name}: {"signature OK" if ok else "BAD SIGNATURE"}')
        return 0 if ok else 1
    print(__doc__)
    return 2


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
