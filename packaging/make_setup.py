"""Pack the app folder onto the installer program: Dannify-Setup-<version>.exe.

    python packaging/make_setup.py <app-dir> <version> <engine.exe> <out.exe>

The layout (read back by installer/Core/Payload.cs):

    [engine exe][payload][trailer]
    payload = [u32 header length][header text][LZMA block][LZMA block]...
    trailer = b'DNFYPAK1' + u64 payload offset + u64 payload length + sha256(payload)

Every file goes into one stream, back to back, and the stream is cut into
fixed-size blocks that are compressed on their own. Separate blocks cost a
little size (about 1 percent here) and buy speed twice over: they compress
in parallel here, and the installer unpacks them in parallel too, so a
fresh install takes seconds rather than most of a minute.

Blocks are raw LZMA1 with explicit properties rather than xz: the installer
carries its own small decoder, and LZMA1 is the simplest thing to decode.
"""

from __future__ import annotations

import hashlib
import lzma
import struct
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BLOCK = 24 * 1024 * 1024
LC, LP, PB = 3, 0, 2
MAGIC = b'DNFYPAK1'


def _order(path: Path) -> tuple:
    # Like with like: machine code together, archives together, the rest
    # after. Neighbours that resemble each other compress better.
    ext = path.suffix.lower()
    group = 0 if ext in ('.exe', '.dll', '.pyd') else 1 if ext in ('.zip', '.res', '.jar') else 2
    return (group, path.as_posix().lower())


def _compress(block: bytes, dict_size: int) -> bytes:
    return lzma.compress(
        block,
        format=lzma.FORMAT_RAW,
        filters=[{
            'id': lzma.FILTER_LZMA1,
            'preset': 9 | lzma.PRESET_EXTREME,
            'dict_size': dict_size,
            'lc': LC,
            'lp': LP,
            'pb': PB,
        }],
    )


def build(app_dir: Path, version: str, engine: Path, out: Path) -> dict:
    app_dir = app_dir.resolve()
    files = sorted((p for p in app_dir.rglob('*') if p.is_file()), key=lambda p: _order(p.relative_to(app_dir)))
    if not files:
        raise SystemExit(f'nothing to pack in {app_dir}')

    entries = []
    stream = bytearray()
    for path in files:
        data = path.read_bytes()
        rel = path.relative_to(app_dir).as_posix()
        if '\n' in rel or '\r' in rel:
            raise SystemExit(f'unpackable file name: {rel!r}')
        entries.append((len(data), hashlib.sha256(data).hexdigest(), rel))
        stream += data
    total = len(stream)

    blocks = [bytes(stream[i:i + BLOCK]) for i in range(0, total, BLOCK)]
    dict_size = max(1 << 20, min(BLOCK, 32 << 20))
    started = time.time()
    with ThreadPoolExecutor(max_workers=min(8, len(blocks))) as pool:
        packed = list(pool.map(lambda b: _compress(b, dict_size), blocks))
    elapsed = time.time() - started

    header = ['DPK1', f'version={version}', f'lzma={LC},{LP},{PB},{dict_size}', f'total={total}']
    header += [f'block={len(p)},{len(b)}' for p, b in zip(packed, blocks)]
    header += [f'file={size},{digest},{rel}' for size, digest, rel in entries]
    header.append('end')
    header_bytes = ('\n'.join(header) + '\n').encode('utf-8')

    payload = struct.pack('<I', len(header_bytes)) + header_bytes + b''.join(packed)
    engine_bytes = engine.read_bytes()
    if engine_bytes[-56:-48] == MAGIC:
        raise SystemExit(f'{engine} already carries a payload; build from the plain engine')

    out.parent.mkdir(parents=True, exist_ok=True)
    trailer = MAGIC + struct.pack('<QQ', len(engine_bytes), len(payload)) + hashlib.sha256(payload).digest()
    tmp = out.with_name(out.name + '.part')
    with open(tmp, 'wb') as fh:
        fh.write(engine_bytes)
        fh.write(payload)
        fh.write(trailer)
    tmp.replace(out)

    return {
        'files': len(entries),
        'unpacked': total,
        'packed': sum(len(p) for p in packed),
        'blocks': len(blocks),
        'seconds': elapsed,
        'size': out.stat().st_size,
    }


def main() -> int:
    if len(sys.argv) != 5:
        print(__doc__)
        return 2
    app_dir, version, engine, out = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]), Path(sys.argv[4])
    info = build(app_dir, version, engine, out)
    print(f"  {info['files']} files, {info['unpacked'] / 1048576:.1f} MB -> "
          f"{info['packed'] / 1048576:.1f} MB in {info['blocks']} blocks ({info['seconds']:.0f}s)")
    print(f"  {out.name}: {info['size'] / 1048576:.1f} MB")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
