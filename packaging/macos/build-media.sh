#!/usr/bin/env bash
# Builds dnfmedia for macOS: FFmpeg with only what Dannify uses, the same
# configuration as the Windows build (packaging/mediatool/build.sh).
#
#   bash packaging/macos/build-media.sh [out-dir]     (default: packaging/macos/media)
#
# Needs Xcode's command line tools and curl; on an Intel Mac, nasm too.
# Built for this Mac's processor, for macOS 11 and later.
#
# Licence: LGPL 2.1 or later throughout. No --enable-gpl, no --enable-nonfree,
# and every external library left out but LAME (LGPL). TLS comes from macOS
# itself (Secure Transport), so no OpenSSL or GnuTLS is linked in.
#
# What the app asks of it, and so all that is in it:
#   * yt-dlp's "extract audio" step: AAC copied out of M4A/MP4 into an
#     iPod-flavoured MP4 (aac_adtstoasc), or Opus/Vorbis from WebM/Ogg
#     converted to AAC; its container fix-ups (-f mp4, +faststart).
#   * the streaming fallback: an https input encoded to MP3 (LAME) on a pipe.
#   * reading what a file is (ffmpeg -i), for both.
set -euo pipefail

FFMPEG_VERSION="7.1.2"
FFMPEG_SHA256="089bc60fb59d6aecc5d994ff530fd0dcb3ee39aa55867849a2bbc4e555f9c304"
LAME_VERSION="3.100"
LAME_SHA256="ddfe36cab873794038ae2c1210557ad34857a4b6bdc515785d1da9e175b1da1e"

HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${1:-$HERE/media}"
JOBS="$(sysctl -n hw.ncpu)"
MACHINE="$(uname -m)"
export MACOSX_DEPLOYMENT_TARGET="${MACOSX_DEPLOYMENT_TARGET:-11.0}"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
DEPS="$WORK/deps"
mkdir -p "$DEPS" "$OUT"
cd "$WORK"

fetch() {  # url file sha256
  curl -fsSL --retry 3 -o "$2" "$1"
  echo "$3  $2" | shasum -a 256 -c -
}

echo "== LAME ${LAME_VERSION}"
fetch "https://downloads.sourceforge.net/project/lame/lame/${LAME_VERSION}/lame-${LAME_VERSION}.tar.gz" \
  "lame.tar.gz" "$LAME_SHA256"
tar xf lame.tar.gz
cd "lame-${LAME_VERSION}"
# The export list names a function that is not built (static only here, but
# the line breaks the build of the shared library on some toolchains).
sed -i.orig '/lame_init_old/d' include/libmp3lame.sym
NASM=""
if [ "$MACHINE" = "x86_64" ]; then NASM="--enable-nasm"; fi
# LAME's config.guess predates Apple silicon: say what this is outright.
./configure --build="$(echo "$MACHINE" | sed 's/arm64/aarch64/')-apple-darwin" \
    --prefix="$DEPS" --enable-static --disable-shared \
    --disable-frontend --disable-decoder --disable-gtktest $NASM >/dev/null
make -j"$JOBS" >/dev/null
make install >/dev/null
cd "$WORK"

echo "== FFmpeg ${FFMPEG_VERSION}"
fetch "https://ffmpeg.org/releases/ffmpeg-${FFMPEG_VERSION}.tar.xz" "ffmpeg.tar.xz" "$FFMPEG_SHA256"
tar xf ffmpeg.tar.xz
cd "ffmpeg-${FFMPEG_VERSION}"

./configure \
    --prefix="$WORK/install" \
    --cc=clang \
    --enable-static --disable-shared --pkg-config-flags=--static \
    --extra-cflags="-I$DEPS/include -O2" --extra-ldflags="-L$DEPS/lib" \
    --disable-debug --disable-doc --disable-autodetect --enable-small \
    --disable-everything \
    --disable-ffplay --disable-ffprobe \
    --disable-avdevice --disable-swscale --disable-postproc \
    --enable-pthreads --enable-network --enable-securetransport \
    --enable-libmp3lame \
    --enable-protocol=file,pipe,http,https,tcp,tls \
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
grep -q '^#define CONFIG_SECURETRANSPORT 1' config.h || { echo "no Secure Transport: https would not work" >&2; exit 1; }

make -j"$JOBS" >/dev/null
strip -x ffmpeg
# Stripping drops the signature an Apple silicon Mac needs to run anything.
codesign --force -s - ffmpeg
install -m 755 ffmpeg "$OUT/dnfmedia"
"$OUT/dnfmedia" -hide_banner -version | head -n 1
otool -L "$OUT/dnfmedia"
ls -la "$OUT/dnfmedia"
echo "== done"
