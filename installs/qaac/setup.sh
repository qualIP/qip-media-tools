#!/bin/sh

# http://www.andrews-corner.org/qaac.html
# https://sites.google.com/site/qaacpage/cabinet

set -e -x

d=`pwd`

qaac_ver=2.59
qaac_ver=2.62
qaac_ver=2.65

apple_ver=4.3.1
apple_ver=5.2

WINEPREFIX=${WINEPREFIX:-~/.wine}
test -n "$WINEPREFIX"
test -d "$WINEPREFIX"

# grep -w i386 /var/lib/dpkg/arch || sudo dpkg --add-architecture i386
# sudo apt-get install wine64 wine32

which wine > /dev/null || sudo aptitude install wine
which unzip > /dev/null || sudo aptitude install unzip
which 7z > /dev/null || sudo aptitude install p7zip-full

#test -d qaac-git || git clone https://github.com/nu774/qaac.git qaac-git
#cd qaac-git
#git pull
#cd "$d"

if ! test -d $WINEPREFIX/drive_c/qaac ; then
    test -f qaac_${qaac_ver}.zip || wget https://github.com/nu774/qaac/releases/download/v${qaac_ver}/qaac_${qaac_ver}.zip
    unzip -j qaac_${qaac_ver}.zip "qaac_${qaac_ver}/x64/*" -d $WINEPREFIX/drive_c/qaac/
fi

#find /media/sf_C_DRIVE/ProgramData/ -iname 'AppleApplicationSupport64.msi'
AppleApplicationSupport_msi="/media/sf_C_DRIVE/ProgramData/Apple/Installer Cache/AppleApplicationSupport ${apple_ver}/AppleApplicationSupport.msi"
AppleApplicationSupport_msi="/media/sf_C_DRIVE/ProgramData/Apple/Installer Cache/AppleApplicationSupport64 ${apple_ver}/AppleApplicationSupport64.msi"
AppleApplicationSupport_msi=""

if ! test -d QTfiles64 ; then

    if [ -z "$AppleApplicationSupport_msi" ] ; then
	AppleApplicationSupport_msi="AppleApplicationSupport64.msi"
	if [ ! -e "$AppleApplicationSupport_msi" ] ; then
	    iTunes64Setup="$HOME/Downloads/iTunes64Setup.exe"
	    if [ ! -e "$iTunes64Setup" ] ; then
		echo "Download $iTunes64Setup from https://www.apple.com/itunes/download/" >&2
		exit 1
	    fi
	    7z e "$iTunes64Setup" "$AppleApplicationSupport_msi"
	fi
    fi

    mkdir QTfiles64
    cd QTfiles64
    7z e -y "../$AppleApplicationSupport_msi" \
	 -i'!*AppleApplicationSupport_ASL.dll' \
	 -i'!*AppleApplicationSupport_CoreAudioToolbox.dll' \
	 -i'!*AppleApplicationSupport_CoreFoundation.dll' \
	 -i'!*AppleApplicationSupport_icudt*.dll' \
	 -i'!*AppleApplicationSupport_libdispatch.dll' \
	 -i'!*AppleApplicationSupport_libicu*.dll' \
	 -i'!*AppleApplicationSupport_objc.dll' \
	 -i'!F_CENTRAL_msvc?100*'
    for j in *.dll; do mv -v $j $(echo $j | sed 's/x64_AppleApplicationSupport_//g'); done
    for j in F_CENTRAL_msvcr100*; do mv -v "$j" msvcr100.dll; done
    for j in F_CENTRAL_msvcp100*; do mv -v "$j" msvcp100.dll; done
    cd ..
fi

if ! test -f $WINEPREFIX/drive_c/qaac/CoreAudioToolbox.dll ; then
    cp -v QTfiles64/*.dll $WINEPREFIX/drive_c/qaac
fi
