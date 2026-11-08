#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
version="${CLIPMINT_VERSION:-0.3.0}"
case "$version" in
  *[!a-zA-Z0-9.+~:-]*|"") echo "Invalid package version" >&2; exit 1;;
esac
test -x dist/ClipMint/ClipMint
test -x dist/ClipMint/_internal/tools/ffmpeg
root="build/clipmint-deb"
rm -rf "$root"
mkdir -p "$root/DEBIAN" "$root/opt/clipmint" "$root/usr/share/applications" "$root/usr/share/icons/hicolor/scalable/apps" "$root/usr/share/doc/clipmint" dist-packages
cp -a dist/ClipMint/. "$root/opt/clipmint/"
# Keep the expensive PyInstaller executable for genuine cold starts only.
# Preserve the existing /opt/clipmint/ClipMint shortcut path using a tiny
# Python stdlib IPC entrypoint instead of forcing every hotkey through Qt.
mv "$root/opt/clipmint/ClipMint" "$root/opt/clipmint/ClipMintApp"
install -m 755 packaging/clipmint-launcher.py "$root/opt/clipmint/ClipMint"
install -m 644 packaging/clipmint.desktop "$root/usr/share/applications/clipmint.desktop"
install -m 644 packaging/clipmint.svg "$root/usr/share/icons/hicolor/scalable/apps/clipmint.svg"
install -m 644 LICENSE "$root/usr/share/doc/clipmint/LICENSE-ClipMint"
install -m 644 LICENSES/MIT-legacy.txt "$root/usr/share/doc/clipmint/MIT-legacy.txt"
install -m 644 THIRD-PARTY-NOTICES.md "$root/usr/share/doc/clipmint/THIRD-PARTY-NOTICES.md"
# Identify the precise build source rather than just a moving branch.
source_commit="$(git rev-parse HEAD 2>/dev/null || printf 'unknown')"
cat > "$root/usr/share/doc/clipmint/SOURCE-CODE.txt" <<EOF
ClipMint original source code: GNU AGPLv3-only (AGPL-3.0-only).
Source repository: https://github.com/cryogenized-spec/clipmint-linux
Build commit: ${source_commit}
Source tree at this commit: https://github.com/cryogenized-spec/clipmint-linux/tree/${source_commit}
Corresponding build scripts: packaging/build-deb.sh and .github/workflows/build-linux.yml
Bundled third-party components retain their own licences and source-availability requirements.
See THIRD-PARTY-NOTICES.md and FFmpeg-SOURCE.txt in this directory.
EOF
install -m 644 vendor/fonts/OFL.txt "$root/usr/share/doc/clipmint/OFL-DotGothic16.txt"
install -m 644 vendor/fonts/OFL-CormorantGaramond.txt "$root/usr/share/doc/clipmint/OFL-CormorantGaramond.txt"
cp /usr/share/common-licenses/GPL-3 "$root/usr/share/doc/clipmint/GPL-3-FFmpeg"
cat > "$root/usr/share/doc/clipmint/FFmpeg-SOURCE.txt" <<'EOF'
Bundled FFmpeg: https://github.com/BtbN/FFmpeg-Builds/releases/tag/autobuild-2026-10-31-12-59
Upstream FFmpeg source: https://ffmpeg.org/download.html
FFmpeg is invoked as a separate GPL command-line executable.
EOF
cat > "$root/DEBIAN/control" <<EOF
Package: clipmint
Version: ${version}
Section: utils
Priority: optional
Architecture: amd64
Maintainer: ClipMint contributors
Depends: libc6 (>= 2.39), python3, xdotool
Recommends: tesseract-ocr, tesseract-ocr-eng
Description: Clipboard manager, screenshot tool, and screen recorder
 Native application for Linux Mint 22 Cinnamon/X11 with bundled
 Python, Qt and FFmpeg. No runtime network dependencies.
EOF
dpkg-deb --root-owner-group --build "$root" "dist-packages/clipmint_${version}_amd64.deb"
dpkg-deb --info "dist-packages/clipmint_${version}_amd64.deb"
# Relative filenames let users verify .deb and SHA256SUMS side by side.
(cd dist-packages && sha256sum "clipmint_${version}_amd64.deb" > SHA256SUMS)
