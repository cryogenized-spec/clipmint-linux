#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
test -x dist/ClipMint/ClipMint
test -x dist/ClipMint/_internal/tools/ffmpeg
root="build/clipmint-deb"
rm -rf "$root"
mkdir -p "$root/DEBIAN" "$root/opt/clipmint" "$root/usr/share/applications" "$root/usr/share/icons/hicolor/scalable/apps" "$root/usr/share/doc/clipmint" dist-packages
cp -a dist/ClipMint/. "$root/opt/clipmint/"
install -m 644 packaging/clipmint.desktop "$root/usr/share/applications/clipmint.desktop"
install -m 644 packaging/clipmint.svg "$root/usr/share/icons/hicolor/scalable/apps/clipmint.svg"
install -m 644 LICENSE "$root/usr/share/doc/clipmint/LICENSE-ClipMint"
install -m 644 vendor/fonts/OFL.txt "$root/usr/share/doc/clipmint/OFL-DotGothic16.txt"
cp /usr/share/common-licenses/GPL-3 "$root/usr/share/doc/clipmint/GPL-3-FFmpeg"
cat > "$root/usr/share/doc/clipmint/FFmpeg-SOURCE.txt" <<'EOF'
Bundled FFmpeg: https://github.com/BtbN/FFmpeg-Builds/releases/tag/autobuild-2026-10-31-12-59
Upstream FFmpeg source: https://ffmpeg.org/download.html
FFmpeg is invoked as a separate GPL command-line executable.
EOF
cat > "$root/DEBIAN/control" <<'EOF'
Package: clipmint
Version: 0.3.0
Section: utils
Priority: optional
Architecture: amd64
Maintainer: ClipMint contributors
Depends: libc6 (>= 2.39)
Description: Clipboard manager, screenshot tool, and screen recorder
 Native application for Linux Mint 22 Cinnamon/X11 with bundled
 Python, Qt and FFmpeg. No runtime network dependencies.
EOF
dpkg-deb --root-owner-group --build "$root" "dist-packages/clipmint_0.3.0_amd64.deb"
dpkg-deb --info "dist-packages/clipmint_0.3.0_amd64.deb"
sha256sum "dist-packages/clipmint_0.3.0_amd64.deb" > "dist-packages/SHA256SUMS"
