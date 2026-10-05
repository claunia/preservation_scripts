#!/usr/bin/env bash
set -euo pipefail
mkdir -p _work

encode_one() {
  local f=$1
  local b=_work/$(basename "${f%.*}")
  case "${f,,}" in
    *.jpg|*.jpeg)
      jpegtran -optimize -copy none "$f" > "$b.jpg"; return ;;
  esac

  magick "$f" -alpha off -strip "$b.src.png"
  cp "$b.src.png" "$b.png"

  # Run both encoders concurrently
  oxipng -t 2 -o max --zopfli --strip all -i 0 -q "$b.png" & local p_png=$!
  opj_compress -i "$b.src.png" -o "$b.jp2" >/dev/null & local p_jp2=$!
  wait "$p_png"
  wait "$p_jp2"

  if [ "$(stat -c%s "$b.jp2")" -lt "$(stat -c%s "$b.png")" ]; then
    rm "$b.png"; else rm "$b.jp2"; fi
  rm "$b.src.png"
}
export -f encode_one

# Process several files in parallel too (default: half the cores,
# since each file already spawns two encoders)
JOBS=${JOBS:-$(( $(nproc) / 2 > 0 ? $(nproc) / 2 : 1 ))}
printf '%s\0' "$@" | xargs -0 -n1 -P "$JOBS" bash -c 'encode_one "$1"' _

img2pdf $(ls -v _work/*.{png,jp2,jpg} 2>/dev/null) -o tmp.pdf
qpdf --object-streams=generate --compress-streams=y tmp.pdf output.pdf
rm tmp.pdf