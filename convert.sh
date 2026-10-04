#!/bin/bash

# For each subdirectory, but not files, in the current directory
for d1 in */ ; do
    [ -d "$d1" ] || continue
    # Enter the subdirectory
    cd "$d1" || continue

    # For each file with the .aif extension, echo the filename
    for f in *.aif ; do
        if [ -e "$f" ]; then
            echo "$f"
            /mnt/datos2/Aaru/6.0/aaru i --logfile "${f%.aif}.convert.log" convert --creator "Nat Portillo" --generate-subchannels "$f" "${f%.aif}.compressed.aif"
            /mnt/datos2/Aaru/6.0/aaru i --logfile "${f%.aif}.compare.log" compare "$f" "${f%.aif}.compressed.aif"
        fi
    done

    # For each subdirectory, but not file, in the current directory
    for d2 in */ ; do
        [ -d "$d2" ] || continue
        # Enter the subdirectory
        cd "$d2" || continue

        # For each file with the .aif extension, echo the filename
        for f in *.aif ; do
            if [ -e "$f" ]; then
                echo "$f"
                /mnt/datos2/Aaru/6.0/aaru i --logfile "${f%.aif}.convert.log" convert --creator "Nat Portillo" --generate-subchannels "$f" "${f%.aif}.compressed.aif"
                /mnt/datos2/Aaru/6.0/aaru i --logfile "${f%.aif}.compare.log" compare "$f" "${f%.aif}.compressed.aif"
            fi
        done

        # For each subdirectory, but not file, in the current directory
        for d2 in */ ; do
            [ -d "$d2" ] || continue
            # Enter the subdirectory
            cd "$d2" || continue

            # For each file with the .aif extension, echo the filename
            for f in *.aif ; do
                if [ -e "$f" ]; then
                    echo "$f"
                    /mnt/datos2/Aaru/6.0/aaru i --logfile "${f%.aif}.convert.log" convert --creator "Nat Portillo" --generate-subchannels "$f" "${f%.aif}.compressed.aif"
                    /mnt/datos2/Aaru/6.0/aaru i --logfile "${f%.aif}.compare.log" compare "$f" "${f%.aif}.compressed.aif"
                fi
            done

            # Exit the subdirectory
            cd ..
        done

        # Exit the subdirectory
        cd ..
    done

    # Exit the subdirectory
    cd ..
done
