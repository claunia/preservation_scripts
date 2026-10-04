#!/bin/bash
/mnt/datos/Aaru/aaru m --logfile "$1.log" dump --first-pregap --fix-offset --persistent -p 3 --fix-subchannel-position --retry-subchannel --fix-subchannel --fix-subchannel-crc --generate-subchannels --metadata=false --eject -O compress=false --title-keys=false --raw /dev/sr0 "$1.aif"
