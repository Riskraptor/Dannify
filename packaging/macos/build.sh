#!/usr/bin/env bash
# Build Dannify.app for macOS and pack it as the release files:
#
#   macos-Dannify-<version>-<arch>.zip   what the app updates itself from
#   macos-Dannify-<version>-<arch>.dmg   what people download and open
#
#   bash packaging/macos/build.sh [out-dir]          (default: packaging/macos/out)
#
# Needs: Xcode's command line tools; a Python (PYTHON, default python3) with
# Backend/requirements.txt and PyInstaller installed; the interface built
# (frontend/dist); the media tool built (bash packaging/macos/build-media.sh).
# QuickJS-ng is built here from its release source, checked against the
# checksum pinned below. Needs cmake.
#
# The app is signed ad hoc (no Apple Developer ID) and not notarised: see
# README.md for what that means on first open. The files are not signed with
# the release key either; the release machine does that before publishing.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
OUT="${1:-$HERE/out}"
PYTHON="${PYTHON:-python3}"
VER="$(sed -n "s/^__version__ = '\(.*\)'/\1/p" "$ROOT/Backend/dannify/__init__.py")"
MACHINE="$(uname -m)"
[ -n "$VER" ] || { echo "no version in Backend/dannify/__init__.py" >&2; exit 1; }
[ -f "$ROOT/frontend/dist/index.html" ] || { echo "build the interface first (frontend/dist)" >&2; exit 1; }
[ -x "$HERE/media/dnfmedia" ] || { echo "build the media tool first: bash packaging/macos/build-media.sh" >&2; exit 1; }

case "$MACHINE" in
  arm64) ARCH=arm64 ;;
  x86_64) ARCH=x64 ;;
  *) echo "unsupported processor: $MACHINE" >&2; exit 1 ;;
esac
export MACOSX_DEPLOYMENT_TARGET="${MACOSX_DEPLOYMENT_TARGET:-11.0}"

# QuickJS-ng (MIT), the JavaScript engine yt-dlp needs to play anything from
# YouTube. The project's own macOS binaries are built for macOS 26 and later
# only, so the same release is compiled here, from its source archive, for
# the macOS this app supports.
QJS_VERSION="0.17.0"
QJS_URL="https://github.com/quickjs-ng/quickjs/archive/refs/tags/v${QJS_VERSION}.tar.gz"
QJS_SHA256="559bc4c420475e55c7ab4510adbc562f55d7524d75e8e89d79ce4bb02f5687d9"

BUILD="$HERE/build"
DIST="$HERE/dist"
rm -rf "$BUILD" "$DIST"
mkdir -p "$BUILD" "$OUT" "$HERE/jsruntime"

echo "== QuickJS-ng ${QJS_VERSION}"
curl -fsSL --retry 3 -o "$BUILD/quickjs.tar.gz" "$QJS_URL"
echo "$QJS_SHA256  $BUILD/quickjs.tar.gz" | shasum -a 256 -c -
tar xzf "$BUILD/quickjs.tar.gz" -C "$BUILD"
cmake -S "$BUILD/quickjs-${QJS_VERSION}" -B "$BUILD/quickjs" -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_OSX_DEPLOYMENT_TARGET="$MACOSX_DEPLOYMENT_TARGET" >/dev/null
cmake --build "$BUILD/quickjs" --target qjs_exe -j "$(sysctl -n hw.ncpu)" >/dev/null
install -m 755 "$BUILD/quickjs/qjs" "$HERE/jsruntime/dnfjs"
strip -x "$HERE/jsruntime/dnfjs"
codesign --force -s - "$HERE/jsruntime/dnfjs"
echo 'print(6 * 7)' > "$BUILD/check.js"
[ "$("$HERE/jsruntime/dnfjs" "$BUILD/check.js")" = "42" ] || { echo "QuickJS does not run here" >&2; exit 1; }

echo "== icon"
ICONSET="$BUILD/Dannify.iconset"
mkdir -p "$ICONSET"
SRC="$ROOT/Backend/assets/android-chrome-512x512.png"
for size in 16 32 128 256 512; do
  sips -z "$size" "$size" "$SRC" --out "$ICONSET/icon_${size}x${size}.png" >/dev/null
  double=$((size * 2))
  if [ "$double" -le 512 ]; then
    sips -z "$double" "$double" "$SRC" --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null
  fi
done
iconutil -c icns "$ICONSET" -o "$BUILD/Dannify.icns"

echo "== PyInstaller"
DANNIFY_VERSION="$VER" DANNIFY_ARCH="$MACHINE" DANNIFY_ICNS="$BUILD/Dannify.icns" \
  "$PYTHON" -m PyInstaller --noconfirm --log-level WARN \
    --distpath "$DIST" --workpath "$BUILD/pyinstaller" "$HERE/dannify-macos.spec"
APP="$DIST/Dannify.app"
[ -d "$APP" ] || { echo "PyInstaller made no app" >&2; exit 1; }

echo "== signing (ad hoc)"
# No Developer ID: an ad-hoc signature, which Apple silicon needs for
# anything to run at all, and which lets the updater check that a new
# version arrived whole (codesign --verify).
codesign --force --deep -s - "$APP"
codesign --verify --deep --strict "$APP"
du -sh "$APP"

echo "== release files"
ZIP="$OUT/macos-Dannify-$VER-$ARCH.zip"
DMG="$OUT/macos-Dannify-$VER-$ARCH.dmg"
rm -f "$ZIP" "$DMG"
ditto -c -k --keepParent "$APP" "$ZIP"

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
ditto "$APP" "$STAGE/Dannify.app"
ln -s /Applications "$STAGE/Applications"
cat > "$STAGE/If Dannify does not open.txt" <<'EOF'
Drag Dannify into Applications, then open it from there.

Dannify is not from the App Store and is not notarised by Apple, so the
first time macOS may say it "cannot be opened" or "cannot verify" it.

macOS 15 and later: open Dannify once, then go to System Settings > Privacy &
Security, scroll down, and click "Open Anyway" next to Dannify.

macOS 14 and earlier: right-click (or Control-click) Dannify in Applications,
choose Open, then Open again.

After that it opens normally, and updates itself.
EOF
# hdiutil now and then finds the disk busy on a build machine: try again.
for attempt in 1 2 3; do
  if hdiutil create -volname "Dannify $VER" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null; then
    break
  fi
  [ "$attempt" = 3 ] && { echo "hdiutil could not make the disk image" >&2; exit 1; }
  sleep 5
done
hdiutil verify "$DMG" >/dev/null

ls -la "$ZIP" "$DMG"
echo "Built $ZIP and $DMG"
