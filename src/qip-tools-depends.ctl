### Commented entries have reasonable defaults.
### Uncomment to edit them.
# Source: <source package name; defaults to package name>
Section: misc
Priority: optional
# Homepage: <enter URL here; no default>
Standards-Version: 3.9.2

Package: qip-tools-depends
Version: 1.0
Maintainer: Jean-Sebastien Trottier <jst@qualipsoft.com>
# Pre-Depends: <comma-separated list of packages>
Depends:
    python3,
    python3-setuptools,
    python3-pip | python3-pip3,
    python3-wheel,
    python3-libdiscid,
    swig,
    libdvdread-dev,
    wine,
    progress,
    graphicsmagick,
    cdparanoia,
    ffmpeg,
    mediainfo,
    dvd+rw-mediainfo | dvd+rw-tools,
    libid3-tools,
    id3v2,
    cuetools,
    mkvtoolnix,
    opus-tools,
    mjpegtools,
    tesseract-ocr-eng,
    tesseract-ocr-fra,
    libtesseract-dev,
    lockfile-progs,
    ccextractor,
    udisks2,
    libdvdcss2,
    libavutil-dev,
    libavcodec-dev,
    libexpat1-dev,
    libdvdread-dev,
    libudfread-dev,
# sudo add-apt-repository ppa:team-xbmc/ppa (https://pkgs.org/search/?q=udfread)
Recommends:
    winetricks,
    q4wine,
    sox,
    gddrescue,
    safecopy,
    icoutils,
    mp4v2-utils,
    python3-bs4,
# NOTE: mp4v2-utils: https://www.deb-multimedia.org
# NOTE: libdvdcss2: https://download.videolan.org/pub/debian/stable/
# Suggests: <comma-separated list of packages>
# Provides: <comma-separated list of packages>
# Replaces: <comma-separated list of packages>
# Architecture: all
# Multi-Arch: <one of: foreign|same|allowed>
# Copyright: <copyright file; defaults to GPL2>
# Changelog: <changelog file; defaults to a generic changelog>
# Readme: <README.Debian file; defaults to a generic one>
# Extra-Files: <comma-separated list of additional files for the doc directory>
# Links: <pair of space-separated paths; First is path symlink points at, second is filename of link>
# Files: <pair of space-separated paths; First is file to include, second is destination>
#  <more pairs, if there's more than one file to include. Notice the starting space>
Description: Dependency package for qualIP's Tools
 Dependency package for qualIP's Tools
