# ClipMint: third-party licences and attribution

The repository-level [AGPLv3-only licence](LICENSE) covers original ClipMint
application source and contributions to that source when the relevant rights
permit licensing under AGPL-3.0-only. It **does not** change the licence or
copyright status of third-party components or third-party artwork.

## Original code previously released under MIT

Earlier ClipMint code was publicly released under MIT with
`Copyright (c) 2026 ClipMint contributors`. Those existing permissions
cannot be revoked by a new repository licence. The original MIT notice and
terms are preserved verbatim in [LICENSES/MIT-legacy.txt](LICENSES/MIT-legacy.txt)
for notices and historical source provenance. This is not a promise to offer
new modifications under MIT.

## Bundled or runtime third-party components

- **FFmpeg**, invoked as a separately bundled executable, comes from
  [BtbN FFmpeg Builds](https://github.com/BtbN/FFmpeg-Builds).
  The selected build is marked GPL; its corresponding source and build
  information are referenced in the packaged `FFmpeg-SOURCE.txt`, and the
  installer provides `GPL-3-FFmpeg`. FFmpeg is not relicensed as AGPL.
- **DotGothic16** and **Cormorant Garamond** are distributed under the
  **SIL Open Font License 1.1**. The package retains
  `OFL-DotGothic16.txt` and `OFL-CormorantGaramond.txt`.
  Sources: [DotGothic16](https://github.com/google/fonts/tree/main/ofl/dotgothic16)
  and [Cormorant Garamond](https://github.com/google/fonts/tree/main/ofl/cormorantgaramond).
- **Qt / PySide6** and other Python/runtime libraries are supplied under
  their own upstream licence terms (including applicable Qt LGPL/GPL
  licensing alternatives). The versions bundled by the build must be
  audited and their notices and source/relinking obligations met before
  a publicly marketed production release. The AGPL notice does not
  supersede those upstream requirements.
- **Tesseract OCR**, **xdotool**, system libraries and desktop tools are
  installed or used through their separately licensed distributions.

## Artwork and illustrations

The existing `clipmint/assets/crimson_maid.png` and
`clipmint/assets/kohaku_card.png` are derived from supplied artwork.
They are **not** declared AGPL-licensed by this change. Their copyright
ownership, redistribution permission, and any reuse permissions must be
established separately before asserting that recipients may freely
redistribute or modify them. In particular, the AGPL source-code licence
does not imply a grant of image-asset rights.

## For distributors

Distributors must preserve upstream notices and satisfy both the AGPL
conditions for ClipMint's covered code and the actual licence conditions
for each included component. This inventory is a starting point, **not**
a completed bill of materials or legal compliance certification.

## bsdiff4

The optional binary-delta update feature bundles the `bsdiff4` Python/C
package (BSD-style licensed). It is used only to reconstruct a verified Debian
installer from an exact cached base package and an independently hashed patch.
Upstream: https://pypi.org/project/bsdiff4/
The corresponding upstream licensing notices remain applicable.
