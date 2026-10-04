#!/bin/bash
/mnt/datos2/Aaru/6.0/aaru m --logfile "$1.log" dump --first-pregap --fix-offset --persistent -p 3 --fix-subchannel-position --retry-subchannel --fix-subchannel --fix-subchannel-crc --generate-subchannels --metadata=false --eject -O compress=false /dev/sr1 "$1.aif"
#/mnt/datos2/Aaru/6.0/aaru i --verbose --logfile "$1.verify.log" verify -t "$1.aif"
