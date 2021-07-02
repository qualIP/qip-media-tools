### Commented entries have reasonable defaults.
### Uncomment to edit them.
# Source: <source package name; defaults to package name>
Section: misc
Priority: optional
Homepage: https://github.com/qualIP/qip-media-tools
Standards-Version: 3.9.2

Package: qip-media-tools-depends
Version: 1.0
Maintainer: Jean-Sebastien Trottier <jst@qualipsoft.com>
# Pre-Depends: <comma-separated list of packages>
Depends:
    python3,
    python3-setuptools,
    python3-pip | python3-pip3,
    python3-wheel,
    python3-libdiscid,
    cython3,
    swig,
# XXXJST TODO remove dependency on graphicsmagick
    graphicsmagick,
    cdparanoia,
    cdrdao,
    ffmpeg,
    mediainfo,
    dvd+rw-tools | dvd+rw-mediainfo,
    libid3-tools,
    id3v2,
    cuetools,
    mkvtoolnix,
    opus-tools,
    mjpegtools,
    lockfile-progs,
    icoutils,
    libdvdcss2,
    libavcodec-dev,
    libavdevice-dev,
    libavfilter-dev,
    libavformat-dev,
    libavutil-dev,
    libswscale-dev,
    libdvdread-dev,
    libexpat1-dev,
    libudfread-dev,
# NOTE: libudfread-dev: sudo add-apt-repository ppa:team-xbmc/ppa (https://pkgs.org/search/?q=udfread)
# NOTE: Non-docker SubtitleEdit Depends: tesseract-ocr, libtesseract-dev
Recommends:
    ccextractor,
    sox,
    gddrescue,
    safecopy,
    python3-bs4,
    python3-lxml,
# NOTE: makemkv now bundles ccextractor
Suggests:
    mp4v2-utils,
# Provides: <comma-separated list of packages>
# Replaces: <comma-separated list of packages>
# NOTE: mp4v2-utils: https://www.deb-multimedia.org
# NOTE: libdvdcss2: https://download.videolan.org/pub/debian/stable/
# Architecture: all
# Multi-Arch: <one of: foreign|same|allowed>
Copyright: ../LICENSE.txt
# Changelog: <changelog file; defaults to a generic changelog>
# Readme: <README.Debian file; defaults to a generic one>
# Extra-Files: <comma-separated list of additional files for the doc directory>
# Links: <pair of space-separated paths; First is path symlink points at, second is filename of link>
# Files: <pair of space-separated paths; First is file to include, second is destination>
#  <more pairs, if there's more than one file to include. Notice the starting space>
Description: Dependency package for qualIP's Media Tools
 Dependency package for qualIP's Media Tools
