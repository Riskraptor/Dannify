#!/usr/bin/env bash
# Build the Dannify .deb for Debian and Ubuntu.
#
#   bash packaging/linux/build-deb.sh [out-dir]
#
# Needs: python3 with pip/venv, dpkg-deb, curl, unzip. The interface must be
# built first (frontend/dist); CI and packaging/build.ps1 do that.
#
# The package carries everything it runs: the app's own code (no tests, no
# build leftovers), the built interface, QuickJS (downloaded here and checked
# against its published checksum, never committed) and every Python library
# as a wheel, so installing needs no network. postinst builds a fresh virtual
# environment from those wheels on every install and upgrade, so an upgrade
# always brings the libraries the new version was built with.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="${1:-$ROOT/packaging/out}"
VER="$(sed -n "s/^__version__ = '\(.*\)'/\1/p" "$ROOT/Backend/dannify/__init__.py")"
ARCH="$(dpkg --print-architecture)"
[ -n "$VER" ] || { echo "no version in Backend/dannify/__init__.py" >&2; exit 1; }
[ -f "$ROOT/frontend/dist/index.html" ] || { echo "build the interface first (frontend/dist)" >&2; exit 1; }

# QuickJS, upstream release (MIT). yt-dlp needs a JS engine to play anything
# from YouTube and Ubuntu's own Node is too old for it.
QJS_URL="https://bellard.org/quickjs/binary_releases/quickjs-linux-x86_64-2025-09-13.zip"
QJS_SHA256="648dc418356b7fa627f78bdf43b12a1cfd94bc220fc36520e1320e36c9328d10"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
STAGE="$WORK/dannify_${VER}_${ARCH}"
APP="$STAGE/opt/dannify"
mkdir -p "$STAGE/DEBIAN" "$APP/app" "$APP/frontend" "$APP/jsruntime" "$APP/wheels" \
  "$STAGE/usr/bin" "$STAGE/usr/share/applications" "$STAGE/usr/share/metainfo" \
  "$STAGE/usr/share/mime/packages" "$STAGE/usr/share/doc/dannify" \
  "$STAGE/usr/share/icons/hicolor/512x512/apps" "$STAGE/usr/share/icons/hicolor/192x192/apps"

echo "== app code"
cp "$ROOT/Backend/main.py" "$ROOT/Backend/desktop.py" "$ROOT/Backend/requirements.txt" "$APP/app/"
( cd "$ROOT/Backend" && find dannify -name '*.py' -not -path '*/__pycache__/*' -print0 \
    | xargs -0 -I{} install -D -m 644 {} "$APP/app/{}" )
# The other platforms' shells have no business on Linux.
rm -rf "$APP/app/dannify/shell/windows" "$APP/app/dannify/shell/macos"
mkdir -p "$APP/app/assets"
cp "$ROOT/Backend/assets/android-chrome-512x512.png" "$APP/app/assets/"
cp -r "$ROOT/frontend/dist" "$APP/frontend/dist"

echo "== QuickJS"
if [ "$ARCH" = "amd64" ]; then
  curl -fsSL --retry 3 -o "$WORK/qjs.zip" "$QJS_URL"
  echo "$QJS_SHA256  $WORK/qjs.zip" | sha256sum -c -
  unzip -q -o "$WORK/qjs.zip" -d "$WORK/qjs"
  QJS="$(find "$WORK/qjs" -type f -name qjs | head -n 1)"
  [ -n "$QJS" ] || { echo "no qjs in the QuickJS release" >&2; exit 1; }
  install -m 755 "$QJS" "$APP/jsruntime/dnfjs"
fi

echo "== Python libraries as wheels"
# One set per Python a supported release might have (Ubuntu 22.04 has 3.10,
# Debian 12 3.11, Ubuntu 24.04 3.12, Debian 13 3.13, Ubuntu 26.04 3.14). Only
# a few are compiled; the rest are shared.
python3 -m venv "$WORK/pip"
"$WORK/pip/bin/pip" install -q --upgrade pip
case "$ARCH" in amd64) PLAT=x86_64 ;; arm64) PLAT=aarch64 ;; *) PLAT="$ARCH" ;; esac
# A few libraries publish only source (proxy-tools, load-dotenv): built into
# wheels here once, which then serve every Python version below.
"$WORK/pip/bin/pip" wheel -q --wheel-dir "$APP/wheels" -r "$ROOT/Backend/requirements.txt"
for PYV in 3.10 3.11 3.12 3.13 3.14; do
  "$WORK/pip/bin/pip" download -q --only-binary=:all: --dest "$APP/wheels" --find-links "$APP/wheels" \
    --python-version "$PYV" --implementation cp \
    --platform "manylinux_2_17_$PLAT" --platform "manylinux2014_$PLAT" \
    --platform "manylinux_2_28_$PLAT" --platform "linux_$PLAT" \
    -r "$ROOT/Backend/requirements.txt" \
    || echo "   (no complete set for Python $PYV; that version installs from PyPI)"
done
cp "$ROOT/Backend/requirements.txt" "$APP/requirements.txt"

echo "== desktop files"
install -m 755 "$ROOT/packaging/linux/dannify" "$STAGE/usr/bin/dannify"
install -m 644 "$ROOT/packaging/linux/dannify.desktop" "$STAGE/usr/share/applications/"
install -m 644 "$ROOT/packaging/linux/dannify.metainfo.xml" "$STAGE/usr/share/metainfo/"
install -m 644 "$ROOT/packaging/linux/dannify-mime.xml" "$STAGE/usr/share/mime/packages/dannify.xml"
install -m 644 "$ROOT/Backend/assets/android-chrome-512x512.png" "$STAGE/usr/share/icons/hicolor/512x512/apps/dannify.png"
install -m 644 "$ROOT/Backend/assets/android-chrome-192x192.png" "$STAGE/usr/share/icons/hicolor/192x192/apps/dannify.png"
install -m 644 "$ROOT/packaging/linux/README-UBUNTU.md" "$STAGE/usr/share/doc/dannify/README.md"
{
  echo "Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/"
  echo "Upstream-Name: Dannify"
  echo "Source: https://github.com/DANIELMWENDWA9451/Dannify"
  echo
  echo "Files: *"
  echo "Copyright: Daniel Mwendwa"
  echo "License: MIT"
  sed 's/^$/./; s/^/ /' "$ROOT/LICENSE"
  echo
  echo "Files: opt/dannify/jsruntime/dnfjs"
  echo "Copyright: Fabrice Bellard and Charlie Gordon"
  echo "License: MIT"
  echo " QuickJS, from $QJS_URL"
  echo
  echo "Files: opt/dannify/wheels/*"
  echo "License: various (MIT, BSD, Apache-2.0, Unlicense); see THIRD-PARTY-NOTICES.md"
} > "$STAGE/usr/share/doc/dannify/copyright"
[ -f "$ROOT/THIRD-PARTY-NOTICES.md" ] && install -m 644 "$ROOT/THIRD-PARTY-NOTICES.md" "$STAGE/usr/share/doc/dannify/"

echo "== control"
SIZE="$(du -sk "$STAGE" | cut -f1)"
cat > "$STAGE/DEBIAN/control" <<EOF
Package: dannify
Version: $VER
Section: sound
Priority: optional
Architecture: $ARCH
Installed-Size: $SIZE
Maintainer: Daniel Mwendwa <eb13.61159.22@student.chuka.ac.ke>
Homepage: https://github.com/DANIELMWENDWA9451/Dannify
Depends: python3 (>= 3.10), python3-venv, python3-gi, gir1.2-gtk-3.0,
 gir1.2-webkit2-4.1 | gir1.2-webkit2-4.0, ffmpeg, gstreamer1.0-plugins-good,
 gstreamer1.0-libav, libsecret-tools, pkexec | policykit-1, xdg-utils
Recommends: gir1.2-ayatanaappindicator3-0.1 | gir1.2-appindicator3-0.1,
 gir1.2-keybinder-3.0, gnome-keyring | kwalletmanager
Description: Music player: search, play and keep songs with lyrics
 Dannify searches YouTube Music, plays it, and keeps the songs you save as
 real files with artwork, tags and synced lyrics. It has a tray icon, media
 keys and the desktop's media panel, and updates itself from signed releases.
EOF

for script in postinst prerm postrm; do
  install -m 755 "$ROOT/packaging/linux/debian/$script" "$STAGE/DEBIAN/$script"
done

find "$APP" -type d -exec chmod 755 {} +
find "$APP" -type f -exec chmod 644 {} +
[ -f "$APP/jsruntime/dnfjs" ] && chmod 755 "$APP/jsruntime/dnfjs"

mkdir -p "$OUT"
DEB="$OUT/linux-dannify_${VER}_${ARCH}.deb"
dpkg-deb --root-owner-group -Zxz --build "$STAGE" "$DEB" >/dev/null
echo "Built $DEB ($(du -h "$DEB" | cut -f1))"
