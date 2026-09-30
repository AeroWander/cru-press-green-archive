#!/bin/sh
# Rebuild the site and publish it to GitHub Pages (the gh-pages branch of this repo's origin).
# gh-pages holds only the generated site and is replaced on every publish.
set -e
cd "$(dirname "$0")/.."
python3 _tools/build.py
REMOTE=$(git remote get-url origin)
TMP=$(mktemp -d)
cp -R site/. "$TMP"
touch "$TMP/.nojekyll"
cd "$TMP"
git init -q -b gh-pages
git add -A
git -c user.name="$(git -C "$OLDPWD" config user.name)" -c user.email="$(git -C "$OLDPWD" config user.email)" \
  commit -q -m "Publish site $(date '+%Y-%m-%d %H:%M')"
git push -q --force "$REMOTE" gh-pages
cd /; rm -rf "$TMP"
echo "Published. Live in a minute or two at the GitHub Pages address."
