"""Dannify's release signing key: make it once, sign with it every release.

    python packaging/release_key.py new            make the key (once, ever)
    python packaging/release_key.py public         print the public half
    python packaging/release_key.py sign <kind> <version> <file>
                                                   write <file>.sig
    python packaging/release_key.py verify <kind> <version> <file>
    python packaging/release_key.py sign-release <file>...
                                                   sign each, the kind and version
                                                   read from its release name
    python packaging/release_key.py verify-release <file>...
                                                   check each against PUBLIC_KEY
                                                   in updates.py (no private key)

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

from dannify import release_assets, signing  # noqa: E402

KEY_FILE = Path.home() / '.dannify' / 'release-signing.key'
# Windows' two kinds, and every platform kind release_assets names.
KINDS = ('package', 'installer')


def _known_kind(kind: str) -> bool:
    return kind in KINDS or bool(
        __import__('re').fullmatch(
            r'installer-linux-deb-(amd64|arm64)|app-macos-zip-(arm64|x64)|installer-macos-dmg-(arm64|x64)',
            kind,
        )
    )


def _shipped_public_key() -> str:
    """PUBLIC_KEY exactly as updates.py ships it: what installed copies trust."""

    import re

    text = (Path(__file__).resolve().parent.parent / 'Backend' / 'dannify' / 'updates.py').read_text(
        encoding='utf-8'
    )
    found = re.search(r"^PUBLIC_KEY = '([0-9a-f]{64})'", text, re.M)
    if not found:
        raise SystemExit('PUBLIC_KEY not found in updates.py')
    return found.group(1)


def _described(path: Path) -> tuple[str, str]:
    found = release_assets.describe(path.name)
    if not found:
        raise SystemExit(f'{path.name} is not named like a release file')
    return found


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
    if not _known_kind(kind):
        raise SystemExit(f'unknown kind {kind!r}')
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
    if command == 'sign-release' and len(argv) > 1:
        secret = load_secret()
        if signing.public_key(secret).hex() != _shipped_public_key():
            raise SystemExit('this key is not the one installed copies trust (PUBLIC_KEY)')
        for name in argv[1:]:
            path = Path(name)
            kind, version = _described(path)
            print(f'  signed {path.name} as {kind} {version} -> {sign_file(kind, version, path, secret).name}')
        return 0
    if command == 'verify-release' and len(argv) > 1:
        public, bad = _shipped_public_key(), 0
        for name in argv[1:]:
            path = Path(name)
            kind, version = _described(path)
            sig = path.with_name(path.name + '.sig')
            ok = sig.is_file() and signing.verify_release(
                public, kind, version, signing.sha256_file(path), sig.read_text(encoding='ascii')
            )
            bad += not ok
            print(f'  {path.name} ({kind} {version}): {"signature OK" if ok else "BAD SIGNATURE"}')
        return 1 if bad else 0
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
