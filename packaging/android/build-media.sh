#!/usr/bin/env bash
# Builds libdnfmedia.so for the Android app: FFmpeg with only what Dannify
# uses, the same configuration as the Windows and macOS builds
# (packaging/mediatool/build.sh, packaging/macos/build-media.sh), for one of
# the processors Android runs on.
#
#   bash packaging/android/build-media.sh <abi> [out-dir]
#
#   abi      arm64-v8a (phones) or x86_64 (the emulator on a PC)
#   out-dir  default android/native; the program lands in <out-dir>/<abi>/
#
# Needs Android's NDK (ANDROID_NDK_HOME, or on a GitHub runner the newest
# one, ANDROID_NDK_LATEST_HOME), make and curl, on Linux.
#
# It is a program, not a library. Android runs programs only from an app's
# native library folder, so it is named like one and installed there with
# the app (android/app/build.gradle.kts: useLegacyPackaging).
#
# Licence: LGPL 2.1 or later throughout, as on the desktops. No --enable-gpl,
# no --enable-nonfree, and every external library left out but LAME (LGPL).
#
# What the app asks of it on a phone:
#   * yt-dlp's "extract audio" step: AAC copied out of M4A/MP4 into an
#     iPod-flavoured MP4 (aac_adtstoasc), or Opus/Vorbis from WebM/Ogg
#     converted to AAC; its container fix-ups (-f mp4, +faststart).
#   * reading what a file is (ffmpeg -i).
# Not the desktops' streaming fallback, which reads an https address: Android
# has no TLS library for a program to link against, and a phone's player
# seeks the stream itself (Backend/dannify/streaming.py).
set -euo pipefail

FFMPEG_VERSION="7.1.2"
FFMPEG_SHA256="089bc60fb59d6aecc5d994ff530fd0dcb3ee39aa55867849a2bbc4e555f9c304"
LAME_VERSION="3.100"
LAME_SHA256="ddfe36cab873794038ae2c1210557ad34857a4b6bdc515785d1da9e175b1da1e"
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
  arm64-v8a) TRIPLE=aarch64-linux-android; ARCH=aarch64; CPU=(--cpu=armv8-a); ASM=() ;;
  # Only the emulator runs this one: no assembly, so no nasm to install.
  x86_64) TRIPLE=x86_64-linux-android; ARCH=x86_64; CPU=(); ASM=(--disable-x86asm) ;;
  *) echo "unknown abi: $ABI" >&2; exit 1 ;;
esac
CC="$TOOLS/${TRIPLE}${API}-clang"

mkdir -p "$OUT/$ABI"
# Where it goes, said in full: the build works in a folder of its own.
OUT="$(cd "$OUT" && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
DEPS="$WORK/deps"
mkdir -p "$DEPS"
cd "$WORK"

fetch() {  # url file sha256
  # Every failure retried, a dropped connection too: a release's build once
  # stopped on "Connection reset by peer" halfway through FFmpeg.
  curl -fsSL --retry 6 --retry-all-errors --retry-delay 10 -o "$2" "$1"
  echo "$3  $2" | sha256sum -c -
}

# LAME and FFmpeg are other people's code: their own warnings are theirs to
# fix, and they buried every real message in this build. Built quietly.
QUIET_CFLAGS="-O2 -w"
# Phones with 16 KB memory pages (Android 15 on) load only programs laid out
# for them; the layout works on 4 KB pages too.
PAGES="-Wl,-z,max-page-size=16384"

echo "== LAME ${LAME_VERSION} for ${ABI}"
fetch "https://downloads.sourceforge.net/project/lame/lame/${LAME_VERSION}/lame-${LAME_VERSION}.tar.gz" \
  lame.tar.gz "$LAME_SHA256"
tar xf lame.tar.gz
cd "lame-${LAME_VERSION}"
# The export list names a function that is not built; static only, so it
# does not matter, but the line stops the link of the shared library.
sed -i '/lame_init_old/d' include/libmp3lame.sym
# The same two fixes to LAME's 2017 build files as the Windows build: make
# warned about prerequisites on a suffix rule, and configure printed a page
# about cross compiling although it works the type sizes out at compile time
# all the same. The 80-bit float check cannot run when cross compiling; "no"
# is what it took without asking.
sed -i 's/^\(\.nas\.l\?o\): \$< nasm\.h$/\1:/' libmp3lame/i386/Makefile.in
sed -i 's/^if test ${cross_compiling} = "yes"; then$/if false; then/' configure
# AR_FLAGS: ar ignores the 'u' in libtool's 'cru', and said so for each library.
# Every tool named outright: the NDK's are not called after the host, and
# configure warned about any it found only under its plain name.
CC="$CC" AR="$TOOLS/llvm-ar" RANLIB="$TOOLS/llvm-ranlib" STRIP="$TOOLS/llvm-strip" \
NM="$TOOLS/llvm-nm" OBJDUMP="$TOOLS/llvm-objdump" AR_FLAGS=cr \
CFLAGS="$QUIET_CFLAGS" alex_cv_ieee854_float80=no \
./configure --host="$TRIPLE" --prefix="$DEPS" --enable-static --disable-shared \
    --disable-frontend --disable-decoder --disable-gtktest >/dev/null
make -j"$JOBS" >/dev/null
make install >/dev/null
cd "$WORK"

echo "== FFmpeg ${FFMPEG_VERSION} for ${ABI}"
fetch "https://ffmpeg.org/releases/ffmpeg-${FFMPEG_VERSION}.tar.xz" ffmpeg.tar.xz "$FFMPEG_SHA256"
tar xf ffmpeg.tar.xz
cd "ffmpeg-${FFMPEG_VERSION}"

./configure \
    --prefix="$WORK/install" \
    --target-os=android --arch="$ARCH" "${CPU[@]}" --enable-cross-compile \
    --cc="$CC" --ar="$TOOLS/llvm-ar" --nm="$TOOLS/llvm-nm" \
    --ranlib="$TOOLS/llvm-ranlib" --strip="$TOOLS/llvm-strip" \
    --enable-static --disable-shared "${ASM[@]}" \
    --extra-cflags="-I$DEPS/include -O2" --extra-ldflags="-L$DEPS/lib $PAGES" \
    --disable-debug --disable-doc --disable-autodetect --enable-small \
    --disable-everything \
    --disable-ffplay --disable-ffprobe \
    --disable-avdevice --disable-swscale --disable-postproc \
    --enable-pthreads \
    --enable-libmp3lame \
    --enable-protocol=file,pipe \
    --enable-demuxer=mov,matroska,ogg,mp3,aac,wav,flac \
    --enable-muxer=ipod,mp4,mov,mp3,adts,matroska,webm,ogg,opus,wav,flac,null \
    --enable-decoder=aac,aac_latm,opus,vorbis,mp3,mp3float,flac,alac,pcm_s16le,pcm_s24le,pcm_f32le \
    --enable-encoder=aac,libmp3lame,pcm_s16le,flac \
    --enable-parser=aac,aac_latm,opus,vorbis,mpegaudio,flac \
    --enable-bsf=aac_adtstoasc,extract_extradata,null \
    --enable-filter=abuffer,abuffersink,aformat,anull,aresample,atrim,volume,acopy,asetnsamples \
    --enable-swresample >/dev/null

# Never anything GPL or non-free, whatever the configure line above becomes.
if grep -E '^#define CONFIG_(GPL|NONFREE) 1' config.h; then
  echo "this FFmpeg build is not LGPL" >&2
  exit 1
fi

make -j"$JOBS" ECFLAGS=-w >/dev/null
"$TOOLS/llvm-strip" ffmpeg
install -m 755 ffmpeg "$OUT/$ABI/libdnfmedia.so"

# What it is, and that it asks a phone for nothing but Android's own C
# library: anything else named here would not be there to load.
PROGRAM="$OUT/$ABI/libdnfmedia.so"
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
