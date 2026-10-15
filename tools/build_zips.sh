#!/bin/zsh
# Build installable ZIPs for Kodi's "Install from zip file" into dist/.
# Each ZIP holds a single top-level folder named after the add-on id, as Kodi requires.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/dist"
mkdir -p "$OUT"
python3 "$ROOT/tools/gen_wall_xml.py" >/dev/null
for id in skin.kscape script.kscape.wall; do
    version=$(sed -nE 's/.*<addon id="'$id'" version="([^"]+)".*/\1/p' "$ROOT/$id/addon.xml")
    zip="$OUT/$id-$version.zip"
    rm -f "$zip"
    (cd "$ROOT" && zip -qr "$zip" "$id" -x '*/__pycache__/*' '*.DS_Store' "$id/tests/*")
    echo "$zip"
done
