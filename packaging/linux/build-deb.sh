#!/usr/bin/env bash
# Builds Dannify Ubuntu DEB (all-Ubuntu compatible, Architecture: all).
# Usage: bash packaging/linux/build-deb.sh [--no-frontend]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VER="$(python3 -c "import re;print(re.search(r\"__version__\s*=\s*'([^']+)'\", open('$ROOT/Backend/dannify/__init__.py').read()).group(1))")"
PKG="dannify_${VER}_all"
STAGE="/tmp/$PKG"
rm -rf "$STAGE"
mkdir -p "$STAGE/DEBIAN" "$STAGE/opt/dannify" "$STAGE/usr/bin" "$STAGE/usr/share/applications" "$STAGE/usr/share/icons/hicolor/512x512/apps" "$STAGE/usr/share/doc/dannify"

# Frontend: build if needed (node 20+ works on all Ubuntu; build once, ship dist)
if [ ! -d "$ROOT/frontend/dist" ] && [ "${1:-}" != "--no-frontend" ]; then
  echo "== building frontend =="
  (cd "$ROOT/frontend" && npm ci && npm run build)
fi

# Payload: Backend (incl. desktop_linux.py) + built frontend + linux packaging
cp -a "$ROOT/Backend" "$STAGE/opt/dannify/"
rm -rf "$STAGE/opt/dannify/__pycache__" "$STAGE/opt/dannify/venv" "$STAGE/opt/dannify/dist"
if [ -d "$ROOT/frontend/dist" ]; then
  mkdir -p "$STAGE/opt/dannify/frontend"
  cp -a "$ROOT/frontend/dist" "$STAGE/opt/dannify/frontend/"
fi
cp -a "$ROOT/packaging/linux/dannify" "$STAGE/usr/bin/dannify"
cp -a "$ROOT/packaging/linux/dannify.desktop" "$STAGE/usr/share/applications/"
# Icon: prefer 512px, fallback to ico->png via existing asset
ICON_SRC="$ROOT/Backend/assets/android-chrome-512x512.png"
[ -f "$ICON_SRC" ] || ICON_SRC="$ROOT/frontend/public/android-chrome-512x512.png"
cp -a "$ICON_SRC" "$STAGE/usr/share/icons/hicolor/512x512/apps/dannify.png"
cp -a "$ROOT/packaging/linux/requirements-linux.txt" "$STAGE/opt/dannify/"
[ -f "$ROOT/packaging/linux/README-UBUNTU.md" ] && cp -a "$ROOT/packaging/linux/README-UBUNTU.md" "$STAGE/usr/share/doc/dannify/"
cp -a "$ROOT/LICENSE" "$STAGE/usr/share/doc/dannify/copyright" 2>/dev/null || echo "Dannify (see LICENSE)" > "$STAGE/usr/share/doc/dannify/copyright"
chmod 755 "$STAGE/usr/bin/dannify"

# Control: all-Ubuntu (22.04/24.04/25.04+) — Architecture: all, python3>=3.10
cat > "$STAGE/DEBIAN/control" <<EOF
Package: dannify
Version: $VER
Section: sound
Priority: optional
Architecture: all
Maintainer: Dannify Contributors <dannify@example.com>
Description: Dannify music player (Ubuntu native port)
 Search, play and keep tracks as real files with artwork, tags and
 synced lyrics. Native GTK/WebKit window wrapping the FastAPI backend
 and Vue frontend. Single instance, tray-friendly, media-key aware.
Depends: python3 (>= 3.10), python3-venv, python3-gi, ffmpeg, libwebkit2gtk-4.1-0 | libwebkit2gtk-4.0-37, libcairo2, nodejs | deno | bun
Recommends: quickjs, deno
Suggests: devscripts, lintian
Homepage: https://github.com/DANIELMWENDWA9451/Dannify
EOF

cat > "$STAGE/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
# Create isolated venv once (network required first run); never fail install if offline.
if [ ! -x /opt/dannify/venv/bin/python3 ]; then
  if python3 -m venv --system-site-packages /opt/dannify/venv 2>/dev/null; then
    /opt/dannify/venv/bin/pip install --upgrade pip 2>/dev/null || true
    /opt/dannify/venv/bin/pip install -r /opt/dannify/requirements-linux.txt 2>/dev/null || echo "Dannify: pip install skipped (offline). Run: sudo /opt/dannify/venv/bin/pip install -r /opt/dannify/requirements-linux.txt"
  else
    echo "Dannify: python3-venv unavailable; falling back to system python3 (pip install fastapi uvicorn ytmusicapi yt-dlp pywebview manually if needed)."
  fi
fi
update-desktop-database >/dev/null 2>&1 || true
gtk-update-icon-cache -f -t /usr/share/icons/hicolor >/dev/null 2>&1 || true
exit 0
EOF

cat > "$STAGE/DEBIAN/prerm" <<'EOF'
#!/bin/sh
set -e
# Ask running copy to quit (best effort, Linux launcher handles --quit).
pkill -f "desktop_linux.py" 2>/dev/null || true
exit 0
EOF
chmod 755 "$STAGE/DEBIAN/postinst" "$STAGE/DEBIAN/prerm"

# Fix perms (flawless lintian: no executables-as-data, no world-writable)
find "$STAGE/opt/dannify" -type d -exec chmod 755 {} \;
find "$STAGE/opt/dannify" -type f -exec chmod 644 {} \;
chmod 755 "$STAGE/usr/bin/dannify"
chmod 644 "$STAGE/usr/share/applications/dannify.desktop" "$STAGE/usr/share/icons/hicolor/512x512/apps/dannify.png"

dpkg-deb --root-owner-group --build "$STAGE" "$ROOT/dannify_${VER}_all.deb"
echo "Built: $ROOT/dannify_${VER}_all.deb"
dpkg-deb --info "$ROOT/dannify_${VER}_all.deb"
dpkg-deb --contents "$ROOT/dannify_${VER}_all.deb" > /tmp/dannify-contents.txt; head -n 40 /tmp/dannify-contents.txt
