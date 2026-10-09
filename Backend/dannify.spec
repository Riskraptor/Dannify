# -*- mode: python ; coding: utf-8 -*-
# Dannify desktop build spec.
#
# Build:  cd Backend & venv\Scripts\pyinstaller --noconfirm dannify.spec
#
# Strategy: ONEDIR (folder) build → instant launches. PyInstaller onefile
# would unpack ~300 MB to %TEMP% on every start (3-8 s); onedir starts in
# well under a second. The installer (installer\) puts the folder in
# <install>\app, behind a small launcher, so nobody sees it.

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None


def build_resources() -> str:
    """Pack what the app reads but does not run into one file.

    The built interface used to ship as a folder of HTML, JavaScript and CSS,
    and clients.json sat beside it. Both were readable, and together they made
    the install folder look like a web page rather than a program. See
    dannify/respack.py for the format and for what this is not.
    """

    sys.path.insert(0, '.')
    from dannify import respack

    members = {}
    ui = Path('..') / 'frontend' / 'dist'
    if not (ui / 'index.html').is_file():
        raise SystemExit(
            'frontend/dist is missing or empty. Run the front-end build first:'
            '\n    cd frontend & npm run build'
        )
    for item in sorted(ui.rglob('*')):
        if item.is_file():
            members['ui/' + item.relative_to(ui).as_posix()] = item.read_bytes()
    # YouTube client identities for the direct resolver. A data file, not code,
    # so a rotated client version can be fixed with a copy in the data dir
    # rather than a rebuild (see _load_clients in dannify/innertube.py).
    members['dannify/clients.json'] = Path('dannify/clients.json').read_bytes()

    out = Path('build') / 'dannify.res'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(respack.pack(members))
    return str(out)


datas = [
    # Interface and data files, in one packed file.
    (build_resources(), '.'),
    # Bundled media encoder (ffmpeg, renamed). Its licence notice is in
    # THIRD-PARTY-NOTICES.md beside the program, as the licence asks.
    # ffprobe is deliberately NOT shipped: nothing in Dannify calls it, and
    # yt-dlp's FFmpegExtractAudio falls back to `ffmpeg -i` for codec probing.
    # Leaving it out takes 97 MB off every install.
    (r'..\packaging\media\dnfmedia.exe', 'media'),
    # Window + tray icon (the exe icon below is separate, baked into the PE).
    (r'assets\dannify.ico', 'assets'),
    # quickjs-ng: the JS engine yt-dlp needs to solve YouTube's signature
    # challenges. Without it every track fails to resolve. 2 MB, MIT.
    (r'..\packaging\jsruntime\dnfjs.exe', 'jsruntime'),
]
# Ship-time config (update repo, Paystack keys): see packaging/config/README.
# PyInstaller puts datas in runtime/, but the app reads <exe dir>/config, so
# packaging\build.ps1 copies that folder in beside the exe after the build.
# ytmusicapi ships JSON locale/context data it loads at runtime.
datas += collect_data_files('ytmusicapi')
# yt-dlp's JS challenge solver scripts (.js data files).
datas += collect_data_files('yt_dlp_ejs', includes=['**/*.js'])

hiddenimports = (
    # uvicorn's dynamically-imported loops/protocols
    [
        'uvicorn.logging',
        'uvicorn.loops', 'uvicorn.loops.auto', 'uvicorn.loops.asyncio',
        'uvicorn.protocols', 'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto', 'uvicorn.protocols.http.h11_impl',
        'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto',
        'uvicorn.protocols.websockets.websockets_impl',
        'uvicorn.lifespan', 'uvicorn.lifespan.on', 'uvicorn.lifespan.off',
        # pywebview Windows backend (WinForms + WebView2 via pythonnet)
        'webview.platforms.winforms', 'webview.platforms.edgechromium',
        'clr_loader', 'pythonnet',
        # app package (lifted out of the bundle into app.pyz below)
        'main',
        'desktop',
    ]
    # yt-dlp lazy-loads extractors by name at runtime
    + collect_submodules('yt_dlp')
    # The other platforms' shells stay out of the Windows program.
    + collect_submodules('dannify', filter=lambda name: not name.startswith(
        ('dannify.shell.linux', 'dannify.shell.macos')))
    + ['yt_dlp_ejs']
)

a = Analysis(
    # boot.py starts the app once its code is where Python finds it; the
    # analysis still follows desktop.py (a hidden import) for everything the
    # app needs.
    ['boot.py'],
    pathex=['.'],
    binaries=[],
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
        'dannify.shell.linux', 'dannify.shell.macos', 'gi',
    ],
    noarchive=False,
    optimize=2,   # strip docstrings/asserts from the shipped bytecode
)



def split_out(pure, wanted, archive):
    """Take the modules `wanted(name)` picks out of the bundle and put them,
    compiled, in their own zip archive. Returns what stays in the bundle.

    An update replaces whole files. With everything in one bundle, a release
    that changed a line of the app's code brought 13 MB of libraries that had
    not changed at all. Now the app's code (app.pyz) and yt-dlp (ytdlp.pyz)
    travel on their own, and the bundle of everything else only when that
    changes. Bytecode only, at the same optimisation as the bundle: nothing
    in them is source.
    """

    import py_compile
    import zipfile

    keep, moved = [], []
    for entry in pure:
        name, src = entry[0], entry[1]
        if wanted(name) and src and str(src).endswith('.py'):
            moved.append((name, src))
        else:
            keep.append(entry)
    out = Path('build') / archive
    work = Path('build') / (archive + '.d')
    work.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, src in sorted(moved):
            parts = name.split('.')
            if Path(src).name == '__init__.py':
                parts.append('__init__')
            arc = '/'.join(parts) + '.pyc'
            pyc = work / (name + '.pyc')
            py_compile.compile(
                str(src), cfile=str(pyc), dfile='/'.join(parts) + '.py', doraise=True, optimize=2,
                invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH,
            )
            info = zipfile.ZipInfo(arc, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, pyc.read_bytes())
    print(f'{archive}: {len(moved)} modules')
    return keep, str(out)


def _is_app(name):
    return name in ('main', 'desktop') or name == 'dannify' or name.startswith('dannify.')


def _is_ytdlp(name):
    return name == 'yt_dlp' or name.startswith('yt_dlp.')


a.pure, _app_pyz = split_out(a.pure, _is_app, 'app.pyz')
a.pure, _ytdlp_pyz = split_out(a.pure, _is_ytdlp, 'ytdlp.pyz')
a.datas += [('app.pyz', _app_pyz, 'DATA'), ('ytdlp.pyz', _ytdlp_pyz, 'DATA')]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

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
    console=False,            # windowed app, no terminal flash
    # A crash must never show a traceback to the person using the app; see
    # _fatal() in desktop.py, which logs the detail and says something useful.
    disable_windowed_traceback=True,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=r'assets\dannify.ico',
    version='version_info.txt',
    # The runtime lives in a folder named for this app rather than
    # PyInstaller's telltale "_internal".
    contents_directory='runtime',
    # The bundle sits beside the program (Dannify.pkg) rather than inside it.
    # Dannify.exe carries the version number, so it changes every release;
    # inside it, the whole bundle came with every update.
    append_pkg=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='Dannify',
)
