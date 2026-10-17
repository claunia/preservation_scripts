#!/bin/bash
# Unified replacement for the dump_*.sh scripts.
#
# Usage: dump_disc.sh [options] <name>
#
# Presets (-t) and what they turn on by default:
#
#   preset          scan  verify  dpm  skip-safedisc  passes  other
#   plain           no    no      yes  no             3                               (dump_dvd*.sh, dump_sr2.sh)
#   paranoia        no    no      yes  no             3       paranoia                (dump_paranoia.sh)
#   pc              yes   no      yes  no             3       paranoia                (dump_pc*.sh)
#   ring            yes   no      yes  no             0       paranoia, --trim=false  (dump_ring*.sh)
#   safedisc        yes   no      yes  YES            3       paranoia                (dump_safedisc.sh)
#   retry-safedisc  no    no      yes  no             1       paranoia, --retry-subchannel=false
#   retry-errors    no    no      NO   no             3       paranoia
#   movie           no    no      NO   no             3       --title-keys=false --raw
#   ngcw            no    no      NO   no             3       --raw
#
#   Hyper-speed is off for every preset. Underscores work too (retry_errors).
#
# Options (override the preset; short and long forms are equivalent):
#   -d, --device DEV         sr0 (default), sr1, sr2, morgay, khepri, or any path/aaru:// URI
#   -t, --preset PRESET      see table above (default: plain)
#   -r, --passes N           number of retry passes (aaru -p N)
#   -R, --start-reverse      retry errors starting from the end (needs a recent aaru)
#   -n, --no-retry-sectors LIST
#                            comma separated sectors or start-end ranges that will
#                            not be trimmed nor retried, e.g. 1234,54000-58000
#                            (needs a recent aaru)
#
#   -K, --skip-safedisc      do NOT retry sectors 800-10000 (SafeDisc area)
#   -k, --no-skip-safedisc   DO retry sectors 800-10000 like any other bad sector
#   -S, --scan               run ProtectionScan before dumping
#   -s, --no-scan            don't run ProtectionScan
#   -V, --verify             verify the image after dumping
#   -v, --no-verify          don't verify
#   -P, --dpm                measure DPM (Data Position Measurement) after dumping
#   -p, --no-dpm             don't measure DPM
#   -H, --hyper-speed        enable --hyper-speed
#   -h, --no-hyper-speed     don't use --hyper-speed
#
#   The settings actually used are printed before the dump starts.
#
# Environment:
#   AARU            aaru binary           (default /mnt/datos2/Aaru/6.0/aaru)
#   PROTECTIONSCAN  ProtectionScan binary (default /mnt/datos2/ProtectionScan/ProtectionScan)
#
# Examples:
#   dump_disc.sh -t pc -H -V Game          # == dump_pc.sh Game
#   dump_disc.sh -t pc -s -d sr1 Game      # == dump_pc_sr1.sh Game
#   dump_disc.sh -t ring -s -V -d morgay X # == dump_ring_morgay.sh X
#   dump_disc.sh --preset retry-errors --skip-safedisc --passes 10 X

AARU="${AARU:-/usr/bin/aaru}"
PROTECTIONSCAN="${PROTECTIONSCAN:-/mnt/datos2/ProtectionScan/ProtectionScan}"

device=sr0
preset=plain
hyper=
verify=
scan=
dpm=
skip_safedisc=
passes=
no_retry_sectors=
reverse=0

args=()
for arg in "$@"; do
    case "$arg" in
        --device)            args+=(-d) ;;
        --preset)            args+=(-t) ;;
        --passes)            args+=(-r) ;;
        --no-retry-sectors)  args+=(-n) ;;
        --start-reverse)     args+=(-R) ;;
        --skip-safedisc)     args+=(-K) ;;
        --no-skip-safedisc)  args+=(-k) ;;
        --scan)              args+=(-S) ;;
        --no-scan)           args+=(-s) ;;
        --verify)            args+=(-V) ;;
        --no-verify)         args+=(-v) ;;
        --dpm)               args+=(-P) ;;
        --no-dpm)            args+=(-p) ;;
        --hyper-speed)       args+=(-H) ;;
        --no-hyper-speed)    args+=(-h) ;;
        --help)              sed -n '2,/^$/p' "$0"; exit 0 ;;
        --*)                 echo "Unknown option: $arg" >&2; exit 1 ;;
        *)                   args+=("$arg") ;;
    esac
done
set -- "${args[@]}"

while getopts "d:t:HhVvSsPpKkr:n:R" opt; do
    case "$opt" in
        d) device="$OPTARG" ;;
        t) preset="$OPTARG" ;;
        H) hyper=1 ;;
        h) hyper=0 ;;
        V) verify=1 ;;
        v) verify=0 ;;
        S) scan=1 ;;
        s) scan=0 ;;
        P) dpm=1 ;;
        p) dpm=0 ;;
        K) skip_safedisc=1 ;;
        k) skip_safedisc=0 ;;
        r) passes="$OPTARG" ;;
        n) no_retry_sectors="$OPTARG" ;;
        R) reverse=1 ;;
        *) sed -n '2,/^$/p' "$0"; exit 1 ;;
    esac
done
shift $((OPTIND - 1))

if [ -z "$1" ]; then
    sed -n '2,/^$/p' "$0"
    exit 1
fi
name="$1"

preset_passes=3
trim=()
extra=()
subchannel_retry=(--retry-subchannel)
preset_scan=0
preset_dpm=1
preset_skip_safedisc=0
preset="${preset//_/-}"  # accept retry_errors as well as retry-errors
case "$preset" in
    plain) ;;
    paranoia) extra=(--paranoia --cure-paranoia) ;;
    pc)       extra=(--paranoia --cure-paranoia); preset_scan=1 ;;
    ring)     extra=(--paranoia --cure-paranoia); preset_passes=0; trim=(--trim=false); preset_scan=1 ;;
    safedisc) extra=(--paranoia --cure-paranoia); preset_scan=1; preset_skip_safedisc=1 ;;
    retry-safedisc) extra=(--paranoia --cure-paranoia); preset_passes=1; subchannel_retry=(--retry-subchannel=false) ;;
    retry-errors) extra=(--paranoia --cure-paranoia); preset_dpm=0 ;;
    movie)    extra=(--title-keys=false --raw); preset_dpm=0 ;;
    ngcw)     extra=(--raw); preset_dpm=0 ;;
    *) echo "Unknown preset: $preset" >&2; exit 1 ;;
esac
# Where each setting comes from, for the summary
origin() { [ -n "$1" ] && echo "option" || echo "preset $preset"; }
o_hyper=$(origin "$hyper"); o_verify=$(origin "$verify"); o_scan=$(origin "$scan")
o_dpm=$(origin "$dpm"); o_skip=$(origin "$skip_safedisc"); o_passes=$(origin "$passes")

hyper="${hyper:-0}"
verify="${verify:-0}"
[ "$hyper" = 1 ] && extra+=(--hyper-speed)
passes="${passes:-$preset_passes}"
if ! [[ "$passes" =~ ^[0-9]+$ ]]; then
    echo "Invalid number of passes: $passes" >&2
    exit 1
fi
if [ -n "$no_retry_sectors" ]; then
    IFS=, read -ra items <<< "$no_retry_sectors"
    for item in "${items[@]}"; do
        if [[ "$item" =~ ^([0-9]+)-([0-9]+)$ ]] && (( BASH_REMATCH[1] <= BASH_REMATCH[2] )); then
            continue
        fi
        if ! [[ "$item" =~ ^[0-9]+$ ]]; then
            echo "Invalid sector list: $no_retry_sectors (expected e.g. 1234,54000-58000)" >&2
            exit 1
        fi
    done
    extra+=(--no-retry-sectors "$no_retry_sectors")
fi
[ "$reverse" = 1 ] && extra+=(--start-reverse)
dpm="${dpm:-$preset_dpm}"
skip_safedisc="${skip_safedisc:-$preset_skip_safedisc}"
[ "$skip_safedisc" = 1 ] && extra+=(--skip-safedisc)
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

yesno() { [ "$1" = 1 ] && echo "yes" || echo "no"; }
echo "Preset:                $preset"
echo "Device:                $dev_path"
echo "Retry passes:          $passes  ($o_passes)"
if [ "$skip_safedisc" = 1 ]; then
    echo "SafeDisc sectors:      SKIPPED, not retried  ($o_skip)"
else
    echo "SafeDisc sectors:      retried like any other  ($o_skip)"
fi
[ "$reverse" = 1 ] && echo "Retry order:           reverse  (option)"
[ -n "$no_retry_sectors" ] && echo "Never retried:         $no_retry_sectors  (option)"
echo "ProtectionScan:        $(yesno "$scan")  ($o_scan)"
echo "Verify after dump:     $(yesno "$verify")  ($o_verify)"
echo "DPM:                   $(yesno "$dpm")  ($o_dpm)"
echo "Hyper-speed:           $(yesno "$hyper")  ($o_hyper)"
echo

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

"$AARU" m --logfile "$name.log" dump --first-pregap --fix-offset --persistent -p "$passes" "${trim[@]}" \
    --fix-subchannel-position "${subchannel_retry[@]}" --fix-subchannel --fix-subchannel-crc \
    --generate-subchannels --metadata=false --eject -O compress=false \
    "${extra[@]}" "$dev_path" "$name.aif"

if [ "$verify" = 1 ]; then
    "$AARU" i --verbose --logfile "$name.verify.log" verify -t "$name.aif"
fi
