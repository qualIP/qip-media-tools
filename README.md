# qualIP's Media Tools

[![Donate](https://img.shields.io/badge/Donate-PayPal-green.svg)](https://www.paypal.com/biz/fund?id=4CZC3J57FXJVE)

*qualIP's Media Tools* is a collection of tools centered on extraction and conversion of multimedia files:

  - Movies -- 3D, HDR, DVD, BD, Matroska, WebM, ...
  - Music -- M4A, FLAC, ...
  - Audiobooks -- M4B, MKA, ...

Table of Contents:
<!--ts-->
* [qualIP's Media Tools](#qualips-media-tools)
* [HOWTOs](#howtos)
* [Tools](#tools)
   * [mmdemux](#mmdemux)
   * [mkbincue / bincuetags / bincuerip](#mkbincue--bincuetags--bincuerip)
   * [mkm4b](#mkm4b)
   * [librivox-dl](#librivox-dl)
   * [lsdvd](#lsdvd)
   * [taged](#taged)
   * [organize-media](#organize-media)
* [Installation](#installation)
* [Donations](#donations)
<!--te-->

# HOWTOs

  - [mmdemux proposed workflow](doc/HOWTO-mmdemux-workflow.md)
  - [Ripping a 3D Movie](doc/HOWTO-rip-3D-movie.md)
  - Soon: Ripping audiobooks from audio CDs
  - Soon: Rip a DVD/BD's main title to .mkv files
  - More in the works...

# Tools

## mmdemux

`mmdemux` is an all-in-one solution for DVD &amp; Blu-ray backup, ripping, extraction and conversion.
It has several unique features including 3D and HDR support.


## mkbincue / bincuetags / bincuerip

These applications manage extraction and ripping of audio CD-ROMs.

`mkbincue` creates bin/cue bit-perfect images from audio CD-ROMs.

`bincuetags` identifies bin/cue images by looking up the MusicBrainz online database.

Finally, `bincuerip` rips audio tracks from bin/cue images into various formats
such as .wav (raw, uncompressed), .m4a (iTunes compression) or .flac (lossless
compression).


## mkm4b

`mkm4v` is an audiobook creator. It combines multiple audio files into a single
audiobook (.m4b or .mka) file, with chapters, tags, picture attachments, etc.


## librivox-dl

`librivox-dl` downloads audiobooks from LibriVox, a site of free public domain
audiobooks. Use in conjunction with `mkm4b` to combine LibriVox's files into
portable audiobook files.


## lsdvd

`lsdvd` is my port of Chris Phillips's original lsdvd to Python. It runs on modern systems and has many fixes and enhancements.


## taged

`taged` is a multimedia tags editor. It provides a single unified interface to edit tags from many different formats, such as Matroska, MP3, MP4, FLAC, etc.


## organize-media

`organize-media` organizes multimedia files (movies, tv-show episodes, music, music
videos, audiobooks) into your library based on tags. Several library
organization schemes are supported to be compatible with your favourite media
library application, such as Plex or Emby.


# Installation

Supported systems:

  - Linux Debian 10 (buster), 11 (bullseye)
  - Linux Ubuntu 20.04.2 LTS (focal)

Support for more systems will be added soon. Feel free to contribute, it's
mostly a question of identifying and installing the right os-specific
packages.

Clone the source code and run `setup`:

    $ git clone https://github.com/qualIP/qip-media-tools.git
    $ cd qip-media-tools
    $ ./setup

    This program will help you install qualIP's Media Tools and its
    dependencies.
    Sudo access will be required to install certain tools.


    ## System Information

    Installation mode: Install
    Installation target: System
    Installation prefix: /usr/local
    Prompt mode: Prompt
    Clean mode: No clean
    LSB release codename: bullseye

    Run `../setup --help` for more options.

    Ready to proceed? [Y/n]

Installation requires installing and building many tools. This process includes:

  - Installing system packages (qip-media-tools-depends and build dependencies)
  - Installing docker and will require you to be added to the `docker` group,
    if you're not already.
  - Compiling and installing 3rd party applications (MakeMKV) and some in their
    own docker (Wine, SubtitleEdit, FRIM, qaac).

This process *will* take a long time, even hours.

More options:

    $ ./setup --help
    Usage: ./setup [options...]
    Options:
      -h, --help          Print this help and exit
      -y, --yes           Answer yes to all prompts (unattended)

      --install           Install (default)
      --reinstall         Reinstall even if already installed
      --uninstall         Uninstall instead of installing

      --user              Select user installation target (~/.local)
      --system            Select system installation target (/usr/local)
      --develop           Select development installation target (~/.local)
      --prefix PREFIX     Specify custom installation prefix

      --clean             Clean build artifacts after installing/uninstalling
      --no-clean          Do not clean build artifacts (default)

For a quick and unattended install at the system level (available to all users). Try this:

    $ sudo ./setup --yes

If you're not setup to run docker yet, the install may stop and request you to
enable docker and re-login before starting setup again to resume:

    You don't seem to be able to run docker commands.
    Try:

        docker info

    You are not part of the docker group. You probably need to run the
    following command to be added to the group:

        sudo adduser $USER docker

    Once done, please start a new login session (or reboot) for the change to
    be effective.

    Please fix the issue and run ./setup again.

Installation completes:

    All done. Enjoy!

# Donations

[![paypal](https://www.paypalobjects.com/en_US/i/btn/btn_donateCC_LG.gif)](https://www.paypal.com/biz/fund?id=4CZC3J57FXJVE)

---

This project is licensed under the terms of the GPL v3.0 license.
