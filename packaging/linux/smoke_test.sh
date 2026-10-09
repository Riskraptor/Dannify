#!/usr/bin/env bash
# Install the built .deb, start Dannify on a virtual screen, check it comes
# up and quits when asked, then remove it and check nothing is left behind.
#
#   sudo bash packaging/linux/smoke_test.sh out/linux-dannify_<v>_amd64.deb
#
# Run by the release workflow on a clean Ubuntu, as root (apt needs it). The
# app itself runs as the unprivileged user named by SUDO_USER, or root.
set -euo pipefail

DEB="$(realpath "$1")"
USER_NAME="${SUDO_USER:-root}"
export DEBIAN_FRONTEND=noninteractive

echo "== install"
# A runner's package index can be days old, and apt then asks for versions
# the archive has already replaced.
apt-get update -q >/dev/null
apt-get install -y -q xvfb dbus-x11 >/dev/null
apt-get install -y -q "$DEB"
test -x /opt/dannify/venv/bin/python3
test -x /usr/bin/dannify
test -x /opt/dannify/jsruntime/dnfjs
/opt/dannify/venv/bin/python3 -c 'import yt_dlp, yt_dlp_ejs, webview, fastapi, gi'
/opt/dannify/jsruntime/dnfjs -e 'console.log("qjs ok")'

echo "== launch"
DATA="$(sudo -u "$USER_NAME" mktemp -d)"
sudo -u "$USER_NAME" env DANNIFY_DATA_DIR="$DATA" DANNIFY_KEYSTORE=file \
  dbus-run-session -- xvfb-run -a dannify >"$DATA/stdout.txt" 2>&1 &
for _ in $(seq 1 90); do
  grep -q 'Application startup complete' "$DATA/dannify.log" 2>/dev/null && break
  sleep 1
done
grep -q 'Application startup complete' "$DATA/dannify.log" || {
  echo "the app did not start"; tail -n 40 "$DATA/dannify.log" "$DATA/stdout.txt" || true; exit 1; }
sleep 10
pgrep -f /opt/dannify/app/desktop.py >/dev/null || { echo "the app did not stay up"; exit 1; }
# A second launch hands over to the first instead of starting again.
sudo -u "$USER_NAME" env DANNIFY_DATA_DIR="$DATA" timeout 20 dannify
test "$(pgrep -fc /opt/dannify/app/desktop.py)" = 1
sudo -u "$USER_NAME" env DANNIFY_DATA_DIR="$DATA" dannify --quit
QUIT_AT=$SECONDS
for _ in $(seq 1 60); do pgrep -f /opt/dannify/app/desktop.py >/dev/null || break; sleep 1; done
if pgrep -f /opt/dannify/app/desktop.py >/dev/null; then
  echo "the app did not quit"; tail -n 25 "$DATA/dannify.log"; exit 1; fi
echo "quit in $((SECONDS - QUIT_AT)) s"
if grep -E 'Traceback|CRITICAL' "$DATA/dannify.log"; then echo "errors in the log"; exit 1; fi

echo "== remove"
apt-get remove -y -q dannify >/dev/null
test ! -e /opt/dannify
test ! -e /usr/bin/dannify
echo "smoke test passed"
