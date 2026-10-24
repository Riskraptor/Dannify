# yt-dlp, as Dannify bundles it. Used in place of the hook yt-dlp ships
# (yt_dlp/__pyinstaller/hook-yt_dlp.py) by both build specs (hookspath).
#
# That hook collects all of urllib3 "just in case", including its browser
# only emscripten module, which cannot be imported outside a browser and
# warns on every build. It also collects curl_cffi's data and names mutagen,
# brotli and secretstorage, none of which Dannify installs or ships (mutagen
# is GPL and kept out on purpose). What it does that Dannify needs is kept.

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

hiddenimports = [
    'yt_dlp.compat._legacy', 'yt_dlp.compat._deprecated',
    'yt_dlp.utils._legacy', 'yt_dlp.utils._deprecated',
    'certifi',
    # websockets is what yt-dlp needs of these three; requests and urllib3
    # for its other request handlers, without urllib3's browser-only part.
    *collect_submodules('websockets'),
    *collect_submodules('requests'),
    *collect_submodules('urllib3', filter=lambda name: not name.startswith('urllib3.contrib.emscripten')),
]

excludedimports = ['youtube_dl', 'youtube_dlc', 'test', 'ytdlp_plugins', 'devscripts', 'bundle']

# The scripts yt-dlp runs to solve YouTube's challenge.
datas = collect_data_files('yt_dlp_ejs', includes=['**/*.js'])
