#!/usr/bin/env bash
set -euo pipefail
version="${CLIPMINT_VERSION:-0.3.0}"
pkg="${1:-dist-packages/clipmint_${version}_amd64.deb}"
test -s "$pkg"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
test "$(dpkg-deb -f "$pkg" Package)" = "clipmint"
test "$(dpkg-deb -f "$pkg" Version)" = "$version"
test "$(dpkg-deb -f "$pkg" Architecture)" = "amd64"
test "$(dpkg-deb -f "$pkg" Depends)" = "libc6 (>= 2.39)"
dpkg-deb --extract "$pkg" "$tmp/unpacked"
dpkg-deb --control "$pkg" "$tmp/control"
test -x "$tmp/unpacked/opt/clipmint/ClipMint"
test -x "$tmp/unpacked/opt/clipmint/_internal/tools/ffmpeg"
test -f "$tmp/unpacked/usr/share/icons/hicolor/scalable/apps/clipmint.svg"
desktop="$tmp/unpacked/usr/share/applications/clipmint.desktop"
desktop-file-validate "$desktop"
grep -Fqx 'Exec=/opt/clipmint/ClipMint' "$desktop"
grep -Fqx 'Terminal=false' "$desktop"
for script in preinst postinst prerm postrm config triggers; do
  if [[ -e "$tmp/control/$script" ]]; then
    echo "Unexpected installer hook: $script" >&2
    exit 1
  fi
done
sudo dpkg --install "$pkg"
test -x /opt/clipmint/ClipMint
set +e
QT_QPA_PLATFORM=xcb XDG_DATA_HOME="$tmp/appdata" \
  xvfb-run -a timeout 10s /opt/clipmint/ClipMint
result="$?"
set -e
if [[ "$result" -ne 124 ]]; then
  echo "Installed application exited early: $result" >&2
  exit 1
fi
xvfb-run -a -s '-screen 0 1280x800x24' bash -c '
  set -euo pipefail
  ffmpeg="$1"
  output="$2"
  "$ffmpeg" -hide_banner -loglevel error -y \
    -f x11grab -framerate 5 -video_size 320x240 \
    -i "${DISPLAY}+0,0" -t 1 -c:v libx264 \
    -preset ultrafast -pix_fmt yuv420p "$output/demo.mp4"
  test -s "$output/demo.mp4"
  "$ffmpeg" -hide_banner -loglevel error -y \
    -f x11grab -framerate 3 -video_size 160x120 \
    -i "${DISPLAY}+0,0" -t 1 -vf fps=3 -f gif "$output/demo.gif"
  test -s "$output/demo.gif"
' _ /opt/clipmint/_internal/tools/ffmpeg "$tmp"
echo "PASS: Installed package launches; bundled FFmpeg creates MP4 and GIF under X11."
