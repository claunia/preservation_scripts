#!/bin/bash
sudo mount -o ro /dev/sr2 /mnt/cdrom2
/mnt/datos2/ProtectionScan/ProtectionScan -j /mnt/cdrom2
sudo umount /mnt/cdrom2
rm protection-2025*.txt
mv protection-2025*.json "$1.protectionscan.json"