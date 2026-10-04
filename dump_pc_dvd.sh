#!/bin/bash
sudo mount -o ro /dev/sr0 /mnt/cdrom
/mnt/datos/ProtectionScan/ProtectionScan -j /mnt/cdrom
sudo umount /mnt/cdrom
/mnt/datos/Aaru/aaru m --logfile "$1.log" dump --first-pregap --fix-offset --persistent -p 3 --fix-subchannel-position --retry-subchannel --fix-subchannel --fix-subchannel-crc --generate-subchannels --metadata=false --eject -O compress=false --paranoia --cure-paranoia /dev/sr0 "$1.aif"
rm protection-2026*.txt
mv protection-2026*.json "$1.protectionscan.json"
