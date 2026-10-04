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
            /home/claunia/Development/Aaru/libaaruformat/tool/aaruformattool upgrade-ddt-to-alpha21 "$f"
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
                /home/claunia/Development/Aaru/libaaruformat/tool/aaruformattool upgrade-ddt-to-alpha21 "$f"
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
                    /home/claunia/Development/Aaru/libaaruformat/tool/aaruformattool upgrade-ddt-to-alpha21 "$f"
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