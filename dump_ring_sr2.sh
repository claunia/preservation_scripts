#!/bin/bash
#sudo mount -o ro /dev/sr2 /mnt/cdrom2
#/mnt/datos2/ProtectionScan/ProtectionScan -j /mnt/cdrom2
#sudo umount /mnt/cdrom2
/mnt/datos2/Aaru/6.0/aaru m --logfile "$1.log" dump --first-pregap --fix-offset --persistent -p 0 --trim=false --fix-subchannel-position --retry-subchannel --fix-subchannel --fix-subchannel-crc --generate-subchannels --metadata=false --eject -O compress=false --paranoia --cure-paranoia /dev/sr2 "$1.aif"
#/mnt/datos2/Aaru/6.0/aaru i --verbose --logfile "$1.verify.log" verify -t "$1.aif"
#rm protection-2025*.txt
#mv protection-2025*.json "$1.protectionscan.json"