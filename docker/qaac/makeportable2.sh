#!/bin/bash

# Inspired by https://sites.google.com/site/qaacpage/cabinet/makeportable2.zip

set -e
set -x

if [[ -e iTunes64Setup.exe ]] ; then
    installer=iTunes64Setup.exe
elif [[ -e iTunesSetup.exe ]] ; then
    installer=iTunesSetup.exe
else
    echo installer executable not found >&2
    exit 1
fi

7z e -y "$installer" iTunes.msi || true
7z e -y "$installer" iTunes64.msi || true

extract() {
    mkdir $1

    if false ; then
        #wine64 msiexec /a $2 /qn TARGETDIR="__TMP__"
        wine64 msiexec /i $2 /qn TARGETDIR="__TMP__"
        __TMP__iTunes=__TMP__/iTunes
    else
        mkdir __TMP__
        7z e -o__TMP__ "$2"
        __TMP__iTunes=__TMP__
        set +x
        for f in "__TMP__/fil"* ; do
            if ! ( file "$f" | grep -q "PE32+ executable (DLL)" ) ; then
                continue
            fi
            name=$(objdump -p "$f" | sed -n -E -e 's/^Name[ \t]+[0-9A-Fa-f]+[ \t]+(\S+\.dll)/\1/p')
            if [[ -n "$name" ]] ; then
                ( set -x && mv -v "$f" "__TMP__/$name" )
            fi
        done
        set -x
    fi

    mv -v $__TMP__iTunes/api-ms-win-*.dll $1 || true
    mv -v $__TMP__iTunes/api_ms_win_*.dll $1 || true
    mv -v $__TMP__iTunes/icudt*.dll $1 || true
    for f in ASL CoreAudioToolbox CoreFoundation libdispatch libicuin libicuuc objc ; do
        mv -v $__TMP__iTunes/$f.dll $1
    done
    if [[ -e __TMP__/System64 ]] ; then
        mv -v __TMP__/System64/*.dll $1
    fi
    if [[ -e __TMP__/System ]] ; then
        mv -v __TMP__/System/*.dll $1
    fi
    if [[ -e __TMP__/Win/System64 ]] ; then
        mv -v __TMP__/Win/System64/*.dll $1
    fi
    if [[ -e __TMP__/Win/System ]] ; then
        mv -v __TMP__/Win/System/*.dll $1
    fi
    rm -Rf __TMP__
}

if [[ -e iTunes.msi ]] ; then
    extract QTfiles iTunes.msi
fi
if [[ -e iTunes64.msi ]] ; then
    extract QTfiles64 iTunes64.msi
fi

if [[ -e iTunes.msi ]] ; then
   rm -v iTunes.msi
fi
if [[ -e iTunes64.msi ]] ; then
   rm -v iTunes64.msi
fi
