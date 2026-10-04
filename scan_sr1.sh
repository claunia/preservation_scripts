#!/bin/bash
sudo mount -o ro /dev/sr1 /mnt/cdrom1
/mnt/datos2/ProtectionScan/ProtectionScan -j /mnt/cdrom1
sudo umount /mnt/cdrom1
rm protection-2025*.txt
mv protection-2025*.json "$1.protectionscan.json"