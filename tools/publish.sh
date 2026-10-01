#!/bin/sh
# Rebuild the site from the clean ROM; with "push" as $1 also push gh-pages (taint must pass first).
set -e
ROM=/d/n64work/dk64/build/dk64_clean.z64
RETAIL=/d/n64work/dk64/rom/baserom.us.z64
SITE=/d/n64work/dk64/site
cd /d/n64work/dk64-cleanroom
python -m games.dk64.taint_report $RETAIL $ROM | head -3 | tee /d/n64work/dk64/build/taint.txt
grep -q "; 0 failing" /d/n64work/dk64/build/taint.txt || { echo "taint not clean: not publishing"; exit 1; }
python ports/ejs/patch_core.py $ROM C:/Users/andre/n64work/mk64/emu/cores_orig /d/n64work/dk64/emu/cores | tail -1
python ports/ejs/make_site.py $ROM C:/Users/andre/n64work/mk64/emu/ejs $SITE
cp /d/n64work/dk64/emu/cores/*.data $SITE/data/cores/
[ "$1" = push ] || exit 0
# one orphan commit per deploy: the Pages builder chokes on a long history of 32 MB ROMs
cd $SITE && git checkout -q --orphan tmp && git add -A && git commit -qm "Site: ${2:-rebuild}" && { git branch -D gh-pages -q 2>/dev/null || true; } && git branch -m gh-pages && git push -q -f origin gh-pages && git gc -q --prune=now && echo "pushed gh-pages"
