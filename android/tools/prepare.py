"""What the Android build needs beside its code, made before every build.

    python android/tools/prepare.py

* app/src/main/assets/dannify.res: the interface (frontend/dist) and the
  YouTube client identities, packed the way the desktop builds pack them
  (Backend/dannify/respack.py). Build the interface first: npm run build.
* app/src/main/jniLibs/<abi>/libdnfjs.so and libdnfmedia.so: QuickJS, the
  JavaScript engine yt-dlp needs to solve YouTube's challenge, and the media
  tool (FFmpeg). Android runs programs only from an app's native library
  folder, so they are installed there as libraries. Both are built for
  Android by .github/workflows/android-native.yml, whose artifact goes in
  android/native/ (see android/README.md).

Runs on any Python 3.10 or later. Writes nothing it does not own.
"""

from __future__ import annotations

import sys
from pathlib import Path

ANDROID = Path(__file__).resolve().parent.parent
ROOT = ANDROID.parent
APP_MAIN = ANDROID / 'app' / 'src' / 'main'

ABIS = ('arm64-v8a', 'x86_64')
PROGRAMS = ('libdnfjs.so', 'libdnfmedia.so')


def pack_interface() -> None:
    sys.path.insert(0, str(ROOT / 'Backend'))
    from dannify import respack  # noqa: PLC0415

    dist = ROOT / 'frontend' / 'dist'
    if not (dist / 'index.html').is_file():
        raise SystemExit('frontend/dist is missing: run npm run build in frontend/ first')
    members = {
        'ui/' + item.relative_to(dist).as_posix(): item.read_bytes()
        for item in sorted(dist.rglob('*')) if item.is_file()
    }
    members['dannify/clients.json'] = (ROOT / 'Backend' / 'dannify' / 'clients.json').read_bytes()
    out = APP_MAIN / 'assets' / 'dannify.res'
    out.parent.mkdir(parents=True, exist_ok=True)
    data = respack.pack(members)
    if not out.is_file() or out.read_bytes() != data:
        out.write_bytes(data)
    print(f'interface: {len(members)} files, {len(data) // 1024} KB')


def copy_programs() -> None:
    for abi in ABIS:
        for name in PROGRAMS:
            made = ANDROID / 'native' / abi / name
            if not made.is_file():
                raise SystemExit(
                    f'{made.relative_to(ROOT)} is missing: download the android-native artifact '
                    '(android/README.md)'
                )
            data = made.read_bytes()
            out = APP_MAIN / 'jniLibs' / abi / name
            if out.is_file() and out.read_bytes() == data:
                continue
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)
            print(f'{name} for {abi}')


if __name__ == '__main__':
    pack_interface()
    copy_programs()
