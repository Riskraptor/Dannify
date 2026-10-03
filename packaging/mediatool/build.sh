#!/usr/bin/env bash
# Builds dnfmedia.exe: FFmpeg for Windows x64 with only what Dannify uses.
# Runs inside a Linux container (see build-media.ps1) and cross-compiles with
# mingw-w64. The full build it replaces was about 100 MB of video codecs,
# subtitle renderers, fonts and devices the app never touches.
#
# What the app asks of it, and so all that is in it:
#   * yt-dlp's "extract audio" step: AAC copied out of M4A/MP4 into an
#     iPod-flavoured MP4 (aac_adtstoasc), or Opus/Vorbis from WebM/Ogg
#     converted to AAC; its container fix-ups (-f mp4, +faststart).
#   * the streaming fallback: an https input read with Windows' own TLS,
#     encoded to MP3 (LAME) on a pipe.
#   * reading what a file is (ffmpeg -i), for both.
set -euo pipefail

FFMPEG_VERSION="${FFMPEG_VERSION:-7.1.2}"
LAME_VERSION="3.100"
HOST=x86_64-w64-mingw32
JOBS="$(nproc)"

apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends \
    mingw-w64 make nasm pkg-config wget ca-certificates xz-utils gcc libc6-dev >/dev/null

mkdir -p /work /deps /out
cd /work

echo "== LAME ${LAME_VERSION}"
wget -q "https://downloads.sourceforge.net/project/lame/lame/${LAME_VERSION}/lame-${LAME_VERSION}.tar.gz"
echo "ddfe36cab873794038ae2c1210557ad34857a4b6bdc515785d1da9e175b1da1e  lame-${LAME_VERSION}.tar.gz" | sha256sum -c -
tar xf "lame-${LAME_VERSION}.tar.gz"
cd "lame-${LAME_VERSION}"
# The export list names a function that is not built; static only, so it
# does not matter, but the line stops the link of the shared library.
sed -i '/lame_init_old/d' include/libmp3lame.sym
./configure --host="$HOST" --prefix=/deps --enable-static --disable-shared \
    --disable-frontend --disable-decoder --disable-gtktest --enable-nasm >/dev/null
make -j"$JOBS" >/dev/null
make install >/dev/null
cd /work

echo "== FFmpeg ${FFMPEG_VERSION}"
wget -q "https://ffmpeg.org/releases/ffmpeg-${FFMPEG_VERSION}.tar.xz"
wget -q "https://ffmpeg.org/releases/ffmpeg-${FFMPEG_VERSION}.tar.xz.asc" || true
tar xf "ffmpeg-${FFMPEG_VERSION}.tar.xz"
cd "ffmpeg-${FFMPEG_VERSION}"

./configure \
    --prefix=/work/install \
    --target-os=mingw32 --arch=x86_64 --cross-prefix="${HOST}-" \
    --enable-static --disable-shared --pkg-config-flags=--static \
    --extra-cflags="-I/deps/include -O2" --extra-ldflags="-L/deps/lib -static" \
    --disable-debug --disable-doc --disable-autodetect --enable-small \
    --disable-everything \
    --disable-ffplay --disable-ffprobe \
    --disable-avdevice --disable-swscale --disable-postproc \
    --enable-w32threads --enable-network --enable-schannel \
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

make -j"$JOBS" >/dev/null
"${HOST}-strip" ffmpeg.exe
cp ffmpeg.exe /out/dnfmedia.exe
./ffmpeg.exe -version >/dev/null 2>&1 || true
ls -la /out/dnfmedia.exe
echo "== done"
