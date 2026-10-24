"""What the Android build needs beside its code, made before every build.

    python android/tools/prepare.py

* app/src/main/assets/dannify.res: the interface (frontend/dist) and the
  YouTube client identities, packed the way the desktop builds pack them
  (Backend/dannify/respack.py). Build the interface first: npm run build.
* app/src/main/jniLibs/<abi>/libdnfjs.so: QuickJS, the JavaScript engine
  yt-dlp needs to solve YouTube's challenge. Android runs programs only from
  an app's native library folder, so it is installed there as a library.
  Downloaded from QuickJS-ng's own release, pinned by checksum; both builds
  are static and need nothing from the phone.
* app/src/main/jniLibs/<abi>/libdnfmedia.so: the media tool (FFmpeg), from
  android/native/<abi>/, where .github/workflows/android-native.yml's
  artifact goes (see android/README.md).

Runs on any Python 3.10 or later. Writes nothing it does not own.
"""

from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

ANDROID = Path(__file__).resolve().parent.parent
ROOT = ANDROID.parent
APP_MAIN = ANDROID / 'app' / 'src' / 'main'

ABIS = ('arm64-v8a', 'x86_64')
QJS_VERSION = 'v0.17.0'
# abi: (file in QuickJS-ng's release, its SHA-256)
QJS = {
    'arm64-v8a': ('qjs-linux-aarch64', '3372133484edf50a69f3c67903af41206d22a061e930e3cfb63269272ef56d2e'),
    'x86_64': ('qjs-linux-x86_64', '0bfc02511a9f549c28b53880d988fc7cd5d361e90c5e8afdfcd7dc6774ceace5'),
}


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


def _download(url: str, sha256: str) -> bytes:
    for attempt in range(6):
        try:
            with urllib.request.urlopen(url, timeout=120) as response:
                data = response.read()
            break
        except OSError:
            if attempt == 5:
                raise
    if hashlib.sha256(data).hexdigest() != sha256:
        raise SystemExit(f'{url} does not match its checksum')
    return data


def fetch_programs() -> None:
    for abi, (name, sha256) in QJS.items():
        out = APP_MAIN / 'jniLibs' / abi / 'libdnfjs.so'
        if out.is_file() and hashlib.sha256(out.read_bytes()).hexdigest() == sha256:
            continue
        url = f'https://github.com/quickjs-ng/quickjs/releases/download/{QJS_VERSION}/{name}'
        data = _download(url, sha256)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        print(f'QuickJS {QJS_VERSION} for {abi}')


def copy_media_tool() -> None:
    for abi in ABIS:
        made = ANDROID / 'native' / abi / 'libdnfmedia.so'
        if not made.is_file():
            raise SystemExit(
                f'{made.relative_to(ROOT)} is missing: download the android-native artifact '
                '(android/README.md)'
            )
        data = made.read_bytes()
        out = APP_MAIN / 'jniLibs' / abi / 'libdnfmedia.so'
        if out.is_file() and out.read_bytes() == data:
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        print(f'media tool for {abi}')


if __name__ == '__main__':
    pack_interface()
    fetch_programs()
    copy_media_tool()
