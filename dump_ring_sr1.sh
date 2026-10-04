#!/bin/bash
#sudo mount -o ro /dev/sr1 /mnt/cdrom1
#/mnt/datos2/ProtectionScan/ProtectionScan -j /mnt/cdrom1
#sudo umount /mnt/cdrom1
/mnt/datos2/Aaru/6.0/aaru m --logfile "$1.log" dump --first-pregap --fix-offset --persistent -p 0 --trim=false --fix-subchannel-position --retry-subchannel --fix-subchannel --fix-subchannel-crc --generate-subchannels --metadata=false --eject -O compress=false --paranoia --cure-paranoia /dev/sr1 "$1.aif"
#/mnt/datos2/Aaru/6.0/aaru i --verbose --logfile "$1.verify.log" verify -t "$1.aif"
#rm protection-2025*.txt
#mv protection-2025*.json "$1.protectionscan.json"