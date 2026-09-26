"""Build the two assets an installed Dannify updates from.

Alongside the installer, every release carries:

  package-<version>.json   every file in the app, with size and SHA-256
  package-<version>.zip    the whole app folder, one entry per file

An installed copy compares its own files against the list, hard-links the
ones that did not change into the new version's folder, and pulls only the
rest out of the zip with range requests (see Backend/dannify/updates.py).
Nothing here is per-version-pair, so a copy of any age updates the same way.

The names are new in 4.0 on purpose. Dannify 3.x looks for manifest-*.json
and files-*.zip and would try to patch its old layout with them; without
them it downloads the installer instead, which is what moves it to the new
layout.

Run from the repository root:
    python packaging/make_update_assets.py <app-dir> <version> <out-dir>
"""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'Backend'))

from dannify import delta  # noqa: E402


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__)
        return 2
    app_dir = Path(sys.argv[1]).resolve()
    version = sys.argv[2]
    out_dir = Path(sys.argv[3]).resolve()
    if not app_dir.is_dir():
        print(f'no such app folder: {app_dir}')
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = delta.build_manifest(app_dir, version)
    manifest_path = out_dir / f'package-{version}.json'
    manifest_path.write_text(json.dumps(manifest, indent=1), encoding='utf-8')

    zip_path = out_dir / f'package-{version}.zip'
    # Deflate per entry, no solid compression: every file has to be
    # independently readable or the range trick does not work.
    with zipfile.ZipFile(
        zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6
    ) as archive:
        for rel in manifest['files']:
            archive.write(app_dir / rel, rel)

    total = sum(f['size'] for f in manifest['files'].values())
    print(f'  files:    {len(manifest["files"])}')
    print(f'  manifest: {manifest_path.name}  ({manifest_path.stat().st_size / 1024:.0f} KB)')
    print(f'  archive:  {zip_path.name}  ({zip_path.stat().st_size / 1048576:.1f} MB '
          f'from {total / 1048576:.1f} MB)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
