#!/usr/bin/env bash
# Package a built Decky plugin into an installable zip.
#
# Usage: package-plugin.sh <plugin-dir> <out-dir> [folder-name]
#
# Decky extracts the zip straight into ~/homebrew/plugins, so the zip holds a
# single top-level folder (folder-name, default: the plugin dir's basename).
# Run `pnpm run build` first; this only collects files, it doesn't compile.
#
# Included: dist/, main.py, plugin.json, package.json, README*, LICENSE*,
# py_modules/, bin/, assets/, backend/ (Python helpers), and defaults/* copied
# to the top level (decky-plugin-template convention). If requirements.txt
# exists its packages are installed into py_modules for Decky's Python 3.11 on
# x86_64 (needs uv). Prints the path of the zip it wrote.
set -euo pipefail

src=$(cd "$1" && pwd)
mkdir -p "$2"
out=$(cd "$2" && pwd)
folder=${3:-$(basename "$src")}
version=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["version"])' "$src/package.json")

for required in dist/index.js main.py plugin.json package.json; do
  [ -e "$src/$required" ] || { echo "missing $required in $src (did you run pnpm run build?)" >&2; exit 1; }
done

stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT
dest="$stage/$folder"
mkdir -p "$dest"

cp -r "$src/dist" "$src/main.py" "$src/plugin.json" "$src/package.json" "$dest/"
for f in "$src"/README* "$src"/LICENSE*; do [ -e "$f" ] && cp "$f" "$dest/"; done
for d in py_modules bin assets backend; do [ -d "$src/$d" ] && cp -r "$src/$d" "$dest/"; done
[ -d "$src/defaults" ] && cp -r "$src/defaults/." "$dest/"

# Decky runs plugins on its bundled CPython 3.11 (x86_64), so dependencies are
# resolved for that, not for whatever Python is on this machine. uv handles
# the cross-target install, including building pure-Python sdists.
if [ -f "$src/requirements.txt" ]; then
  command -v uv >/dev/null || { echo "requirements.txt needs uv: https://docs.astral.sh/uv/" >&2; exit 1; }
  uv pip install --quiet --no-compile --target "$dest/py_modules" --requirement "$src/requirements.txt" \
    --python 3.11 --python-platform x86_64-manylinux_2_28 >&2
fi

find "$dest" \( -name __pycache__ -o -name '*.map' -o -name .keep -o -name .lock \) -prune -exec rm -rf {} +

zip_path="$out/$folder-$version.zip"
rm -f "$zip_path"
(cd "$stage" && zip -qr "$zip_path" "$folder")
echo "$zip_path"
