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
depends="$(dpkg-deb -f "$pkg" Depends)"
for package in 'libc6 (>= 2.39)' 'python3' 'xz-utils' 'xdotool'; do
  [[ ", $depends," == *"$package"* ]] || { echo "Missing dependency $package"; exit 1; }
done
recommends="$(dpkg-deb -f "$pkg" Recommends)"
for package in 'tesseract-ocr' 'tesseract-ocr-eng'; do
  [[ ", $recommends," == *"$package"* ]] || { echo "Missing OCR recommendation $package"; exit 1; }
done
dpkg-deb --extract "$pkg" "$tmp/unpacked"
dpkg-deb --control "$pkg" "$tmp/control"
test -x "$tmp/unpacked/opt/clipmint/ClipMint"
test -x "$tmp/unpacked/opt/clipmint/ClipMintApp"
head -n 1 "$tmp/unpacked/opt/clipmint/ClipMint" | grep -Fqx '#!/usr/bin/python3'
test -f "$tmp/unpacked/opt/clipmint/_internal/assets/manga/kohaku_card.png"
echo "585800ce776353d84a9d60e798ff591d06b580f95be0943a46ae67c1c107817a  $tmp/unpacked/opt/clipmint/_internal/assets/manga/kohaku_card.png" | sha256sum --check
test -x "$tmp/unpacked/opt/clipmint/_internal/tools/ffmpeg"
for name in CormorantGaramond-Regular.ttf CormorantGaramond-Italic.ttf; do
  test -f "$tmp/unpacked/opt/clipmint/_internal/assets/fonts/$name"
done
test -f "$tmp/unpacked/usr/share/doc/clipmint/OFL-CormorantGaramond.txt"
licence_dir="$tmp/unpacked/usr/share/doc/clipmint"
test -s "$licence_dir/LICENSE-ClipMint"
grep -Fqx 'GNU AFFERO GENERAL PUBLIC LICENSE' "$licence_dir/LICENSE-ClipMint"
grep -Fqx 'Version 3, 19 November 2007' "$licence_dir/LICENSE-ClipMint"
grep -Fq '13. Remote Network Interaction' "$licence_dir/LICENSE-ClipMint"
test -s "$licence_dir/MIT-legacy.txt"
test -s "$licence_dir/THIRD-PARTY-NOTICES.md"
test -s "$licence_dir/SOURCE-CODE.txt"
grep -Fq "https://github.com/cryogenized-spec/clipmint-linux" "$licence_dir/SOURCE-CODE.txt"
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
test -x /opt/clipmint/ClipMintApp
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
