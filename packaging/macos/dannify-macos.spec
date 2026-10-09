# -*- mode: python ; coding: utf-8 -*-
# Dannify.app: the PyInstaller build for macOS.
#
# Run by packaging/macos/build.sh, which sets DANNIFY_VERSION, DANNIFY_ARCH
# (arm64 or x86_64) and DANNIFY_ICNS, and provides media/dnfmedia and
# jsruntime/dnfjs beside this file. Like the Windows build (Backend/dannify.spec)
# it is a folder build, inside an app bundle: instant starts, and the whole
# bundle is what an update replaces.

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

HERE = Path(SPECPATH).resolve()  # noqa: F821  (set by PyInstaller)
ROOT = HERE.parents[1]
BACKEND = ROOT / 'Backend'
WORK = HERE / 'build'
VERSION = os.environ['DANNIFY_VERSION']
ARCH = os.environ.get('DANNIFY_ARCH') or None
BUNDLE_ID = 'io.github.danielmwendwa9451.dannify'
TRACK_TYPE = BUNDLE_ID + '.track'

sys.path.insert(0, str(BACKEND))


def build_resources() -> str:
    """The interface and clients.json in one packed file, as on Windows (see
    Backend/dannify.spec and dannify/respack.py): a shipped build serves the
    interface from it and refuses to start without it."""

    from dannify import respack

    ui = ROOT / 'frontend' / 'dist'
    if not (ui / 'index.html').is_file():
        raise SystemExit('frontend/dist is missing: build the interface first (npx vite build)')
    members = {}
    for item in sorted(ui.rglob('*')):
        if item.is_file():
            members['ui/' + item.relative_to(ui).as_posix()] = item.read_bytes()
    members['dannify/clients.json'] = (BACKEND / 'dannify' / 'clients.json').read_bytes()
    out = WORK / 'dannify.res'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(respack.pack(members))
    return str(out)


def tool(folder: str, name: str) -> str:
    path = HERE / folder / name
    if not path.is_file():
        raise SystemExit(f'{path} is missing: see packaging/macos/build.sh')
    return str(path)


datas = [
    (build_resources(), '.'),
    # Dannify's licence and the notices of what it carries, as the licences ask.
    (str(ROOT / 'LICENSE'), '.'),
    (str(ROOT / 'THIRD-PARTY-NOTICES.md'), '.'),
]


def english_only(dest: str) -> bool:
    """ytmusicapi's translations are for a language nothing ever passes it."""

    parts = dest.replace(os.sep, '/').split('/')
    if 'locales' not in parts:
        return True
    rest = parts[parts.index('locales') + 1:]
    return bool(rest) and rest[0] == 'en'


datas += [(src, dest) for src, dest in collect_data_files('ytmusicapi') if english_only(dest)]
datas += collect_data_files('yt_dlp_ejs', includes=['**/*.js'])

binaries = [
    # FFmpeg (LGPL build, see build-media.sh) and QuickJS-ng (MIT), under the
    # names the app looks for (dannify/jsruntime.py).
    (tool('media', 'dnfmedia'), 'media'),
    (tool('jsruntime', 'dnfjs'), 'jsruntime'),
]

hiddenimports = (
    [
        'uvicorn.logging',
        'uvicorn.loops', 'uvicorn.loops.auto', 'uvicorn.loops.asyncio',
        'uvicorn.protocols', 'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto', 'uvicorn.protocols.http.h11_impl',
        'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto',
        'uvicorn.protocols.websockets.websockets_impl',
        'uvicorn.lifespan', 'uvicorn.lifespan.on', 'uvicorn.lifespan.off',
        # pywebview's Cocoa backend and what the macOS shell talks to.
        'webview.platforms.cocoa',
        'objc', 'AppKit', 'Foundation', 'WebKit', 'MediaPlayer', 'Quartz',
        'PyObjCTools', 'PyObjCTools.AppHelper',
        'main',
        'desktop',
    ]
    + collect_submodules('yt_dlp')
    # The other platforms' shells stay out of the Mac program.
    + collect_submodules('dannify', filter=lambda name: not name.startswith(
        ('dannify.shell.windows', 'dannify.shell.linux')))
    + ['yt_dlp_ejs']
)

a = Analysis(
    [str(BACKEND / 'boot.py')],
    pathex=[str(BACKEND)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', 'unittest', 'pydoc_data', 'lib2to3',
        'pytest', '_pytest', 'pip', 'setuptools', 'wheel',
        # GPL: kept out of the program for good, even if it is installed.
        'mutagen',
        'dannify.shell.windows', 'dannify.shell.linux', 'gi', 'clr', 'pythonnet', 'clr_loader',
    ],
    noarchive=False,
    optimize=2,  # strip docstrings and asserts from the shipped bytecode
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Dannify',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=True,
    # Documents opened from Finder arrive as Apple Events, which the shell
    # answers itself (application:openFiles:).
    argv_emulation=False,
    target_arch=ARCH,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='Dannify',
)

app = BUNDLE(
    coll,
    name='Dannify.app',
    icon=os.environ.get('DANNIFY_ICNS') or None,
    bundle_identifier=BUNDLE_ID,
    version=VERSION,
    info_plist={
        'CFBundleName': 'Dannify',
        'CFBundleDisplayName': 'Dannify',
        'CFBundleShortVersionString': VERSION,
        'CFBundleVersion': VERSION,
        # WKWebView's pageZoom, the Now Playing artwork and SF Symbols all
        # need Big Sur.
        'LSMinimumSystemVersion': '11.0',
        'LSApplicationCategoryType': 'public.app-category.music',
        'NSHighResolutionCapable': True,
        'NSRequiresAquaSystemAppearance': False,
        'NSSupportsAutomaticGraphicsSwitching': True,
        'NSHumanReadableCopyright': 'Copyright \N{COPYRIGHT SIGN} Daniel Mwendwa. MIT licence.',
        # The window shows the app's own server, on this Mac only, over http.
        'NSAppTransportSecurity': {'NSAllowsLocalNetworking': True},
        'CFBundleDocumentTypes': [
            {
                'CFBundleTypeName': 'Dannify song',
                'CFBundleTypeRole': 'Viewer',
                'LSHandlerRank': 'Owner',
                'LSItemContentTypes': [TRACK_TYPE],
            },
            {
                'CFBundleTypeName': 'Audio file',
                'CFBundleTypeRole': 'Viewer',
                'LSHandlerRank': 'Alternate',
                'LSItemContentTypes': [
                    'public.mp3', 'public.mpeg-4-audio', 'com.apple.m4a-audio',
                    'org.xiph.flac', 'public.aac-audio', 'com.microsoft.waveform-audio',
                    'org.xiph.ogg-audio', 'org.xiph.opus',
                ],
            },
        ],
        'UTExportedTypeDeclarations': [
            {
                'UTTypeIdentifier': TRACK_TYPE,
                'UTTypeDescription': 'Dannify song',
                'UTTypeConformsTo': ['public.data'],
                'UTTypeTagSpecification': {
                    'public.filename-extension': ['dnf'],
                    'public.mime-type': ['application/x-dannify-track'],
                },
            },
        ],
    },
)
