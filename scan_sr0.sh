#!/bin/bash
sudo mount -o ro /dev/sr0 /mnt/cdrom
/mnt/datos/ProtectionScan/ProtectionScan -j /mnt/cdrom
sudo umount /mnt/cdrom
rm protection-2025*.txt
mv protection-2025*.json "$1.protectionscan.json"
