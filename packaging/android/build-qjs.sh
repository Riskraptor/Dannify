#!/usr/bin/env bash
# Builds libdnfjs.so for the Android app: QuickJS-ng's qjs, the JavaScript
# engine yt-dlp needs to solve YouTube's challenge, for one of the processors
# Android runs on. The same version the desktops carry.
#
#   bash packaging/android/build-qjs.sh <abi> [out-dir]
#
#   abi      arm64-v8a (phones) or x86_64 (the emulator on a PC)
#   out-dir  default android/native; the program lands in <out-dir>/<abi>/
#
# Needs Android's NDK (ANDROID_NDK_HOME, or on a GitHub runner the newest
# one, ANDROID_NDK_LATEST_HOME), cmake, make and curl, on Linux.
#
# Built here rather than taken from QuickJS-ng's release: theirs are Linux
# programs, and their x86_64 one is laid out for 4 KB memory pages only,
# which phones with 16 KB pages do not load. Like the media tool it is a
# program named like a library (see build-media.sh). Licence: MIT.
set -euo pipefail

QJS_VERSION="0.17.0"
QJS_SHA256="559bc4c420475e55c7ab4510adbc562f55d7524d75e8e89d79ce4bb02f5687d9"
# The oldest Android the app runs on (android/app/build.gradle.kts: minSdk).
API=24

ABI="${1:?which processor: arm64-v8a or x86_64}"
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${2:-$HERE/../../android/native}"
NDK="${ANDROID_NDK_HOME:-${ANDROID_NDK_LATEST_HOME:-}}"
[ -d "$NDK" ] || { echo "no NDK: set ANDROID_NDK_HOME" >&2; exit 1; }
TOOLS="$NDK/toolchains/llvm/prebuilt/linux-x86_64/bin"
JOBS="$(nproc)"
case "$ABI" in
  arm64-v8a|x86_64) ;;
  *) echo "unknown abi: $ABI" >&2; exit 1 ;;
esac

mkdir -p "$OUT/$ABI"
# Where it goes, said in full: the build works in a folder of its own.
OUT="$(cd "$OUT" && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
cd "$WORK"

echo "== QuickJS-ng ${QJS_VERSION} for ${ABI}"
# Every failure retried, a dropped connection too.
curl -fsSL --retry 6 --retry-all-errors --retry-delay 10 -o quickjs.tar.gz \
  "https://github.com/quickjs-ng/quickjs/archive/refs/tags/v${QJS_VERSION}.tar.gz"
echo "$QJS_SHA256  quickjs.tar.gz" | sha256sum -c -
tar xf quickjs.tar.gz
cd "quickjs-${QJS_VERSION}"

# Its own warnings are its own to fix (-w), as with LAME and FFmpeg. Laid
# out for 16 KB pages, which works on 4 KB ones too.
cmake -S . -B build -G "Unix Makefiles" \
  -DCMAKE_TOOLCHAIN_FILE="$NDK/build/cmake/android.toolchain.cmake" \
  -DANDROID_ABI="$ABI" -DANDROID_PLATFORM="android-$API" \
  -DANDROID_SUPPORT_FLEXIBLE_PAGE_SIZES=ON \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_C_FLAGS="-w" \
  -DCMAKE_EXE_LINKER_FLAGS="-Wl,-z,max-page-size=16384" \
  -DQJS_ENABLE_INSTALL=OFF -DQJS_BUILD_EXAMPLES=OFF >/dev/null
cmake --build build --target qjs_exe -j"$JOBS" >/dev/null
"$TOOLS/llvm-strip" build/qjs
install -m 755 build/qjs "$OUT/$ABI/libdnfjs.so"

# What it is, and that it asks a phone for nothing but Android's own C
# library: anything else named here would not be there to load.
PROGRAM="$OUT/$ABI/libdnfjs.so"
"$TOOLS/llvm-readelf" -h "$PROGRAM" | grep -E 'Type:|Machine:'
NEEDS="$("$TOOLS/llvm-readelf" -d "$PROGRAM" | sed -n 's/.*(NEEDED).*\[\(.*\)\]/\1/p' | sort | tr '\n' ' ')"
echo "needs: $NEEDS"
for lib in $NEEDS; do
  case "$lib" in
    libc.so|libm.so|libdl.so) ;;
    *) echo "needs $lib, which Android does not have" >&2; exit 1 ;;
  esac
done
# Every part laid out for 16 KB pages.
while read -r align; do
  [ $((align)) -ge 16384 ] || { echo "not laid out for 16 KB pages" >&2; exit 1; }
done < <("$TOOLS/llvm-readelf" -lW "$PROGRAM" | awk '$1 == "LOAD" { print $NF }')
ls -la "$PROGRAM"
echo "== done"
