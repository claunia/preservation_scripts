#!/bin/bash
# Unified replacement for the dump_*.sh scripts.
#
# Usage: dump_disc.sh [options] <name>
#
# Presets (-t):
#   plain     plain dump                                   (dump_dvd*.sh, dump_sr2.sh)
#   paranoia  --paranoia --cure-paranoia                   (dump_paranoia.sh)
#   pc        scan + paranoia                              (dump_pc*.sh)
#   ring      scan + paranoia + -p 0 --trim=false          (dump_ring*.sh)
#   safedisc  scan + paranoia + --skip-safedisc            (dump_safedisc.sh)
#   retry-safedisc  paranoia + -p 1 + --retry-subchannel=false (retries SafeDisc sectors once, no --skip-safedisc)
#   movie     --title-keys=false --raw                     (dump_movie.sh)
#
# Options (applied after the preset, so they override it):
#   -d DEV      sr0 (default), sr1, sr2, morgay, khepri, or any path/aaru:// URI
#   -t PRESET   see above (default: plain)
#   -H / -h     enable / disable --hyper-speed
#   -V / -v     enable / disable verify after dumping
#   -S / -s     enable / disable ProtectionScan before dumping
#   -p          disable DPM (Data Position Measurement)
#
# Environment:
#   AARU            aaru binary           (default /mnt/datos2/Aaru/6.0/aaru)
#   PROTECTIONSCAN  ProtectionScan binary (default /mnt/datos2/ProtectionScan/ProtectionScan)
#
# Examples:
#   dump_disc.sh -t pc -H -V Game          # == dump_pc.sh Game
#   dump_disc.sh -t pc -s -d sr1 Game      # == dump_pc_sr1.sh Game
#   dump_disc.sh -t ring -s -V -d morgay X # == dump_ring_morgay.sh X

AARU="${AARU:-/mnt/datos2/Aaru/6.0/aaru}"
PROTECTIONSCAN="${PROTECTIONSCAN:-/mnt/datos2/ProtectionScan/ProtectionScan}"

device=sr0
preset=plain
hyper=
verify=
scan=
dpm=

while getopts "d:t:HhVvSsp" opt; do
    case "$opt" in
        d) device="$OPTARG" ;;
        t) preset="$OPTARG" ;;
        H) hyper=1 ;;
        h) hyper=0 ;;
        V) verify=1 ;;
        v) verify=0 ;;
        S) scan=1 ;;
        s) scan=0 ;;
        p) dpm=0 ;;
        *) sed -n '2,/^$/p' "$0"; exit 1 ;;
    esac
done
shift $((OPTIND - 1))

if [ -z "$1" ]; then
    sed -n '2,/^$/p' "$0"
    exit 1
fi
name="$1"

retry=(-p 3)
extra=()
subchannel_retry=(--retry-subchannel)
preset_scan=0
case "$preset" in
    plain) ;;
    paranoia) extra=(--paranoia --cure-paranoia) ;;
    pc)       extra=(--paranoia --cure-paranoia); preset_scan=1 ;;
    ring)     extra=(--paranoia --cure-paranoia); retry=(-p 0 --trim=false); preset_scan=1 ;;
    safedisc) extra=(--paranoia --cure-paranoia --skip-safedisc); preset_scan=1 ;;
    retry-safedisc) extra=(--paranoia --cure-paranoia); retry=(-p 1); subchannel_retry=(--retry-subchannel=false) ;;
    movie)    extra=(--title-keys=false --raw) ;;
    *) echo "Unknown preset: $preset" >&2; exit 1 ;;
esac
[ "$hyper" = 1 ] && extra+=(--hyper-speed)
[ "$dpm" = 0 ] && extra+=(--dpm=false)

case "$device" in
    morgay)  dev_path=aaru://morgay/dev/sr0 ;;
    khepri)  dev_path=aaru://khepri/dev/sr0 ;;
    sr[0-9]) dev_path="/dev/$device" ;;
    *)       dev_path="$device" ;;
esac

# Remote devices cannot be mounted, so only scan them if explicitly asked (and fail)
[[ "$dev_path" == /dev/* ]] || preset_scan=0
scan="${scan:-$preset_scan}"

if [ "$scan" = 1 ]; then
    case "$dev_path" in
        /dev/sr0)      mnt=/mnt/cdrom ;;
        /dev/sr[0-9])  mnt="/mnt/cdrom${dev_path#/dev/sr}" ;;
        *) echo "ProtectionScan not possible on $dev_path" >&2; exit 1 ;;
    esac
    out_json="$(realpath -m "$name.protectionscan.json")"
    tmp="$(mktemp -d)"
    sudo mount -o ro "$dev_path" "$mnt"
    (cd "$tmp" && "$PROTECTIONSCAN" -j "$mnt")
    sudo umount "$mnt"
    mv "$tmp"/protection-*.json "$out_json"
    rm -rf "$tmp"
fi

"$AARU" m --logfile "$name.log" dump --first-pregap --fix-offset --persistent "${retry[@]}" \
    --fix-subchannel-position "${subchannel_retry[@]}" --fix-subchannel --fix-subchannel-crc \
    --generate-subchannels --metadata=false --eject -O compress=false \
    "${extra[@]}" "$dev_path" "$name.aif"

if [ "$verify" = 1 ]; then
    "$AARU" i --verbose --logfile "$name.verify.log" verify -t "$name.aif"
fi
