class QipMediaToolsDepends < Formula
  desc "Dependency package for qualIP's Media Tools"
  homepage "https://github.com/qualIP/qip-media-tools"
  license "GPL-3.0-or-later"
  version "1.0"
  revision 1

  url "file:///dev/null"
  sha256 "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

  depends_on "python@3.9"
  #depends_on "python-setuptools"
  #depends_on "python-pip"
  #depends_on "python-wheel"
  depends_on "cython"
  depends_on "swig"
  depends_on "graphicsmagick"
  depends_on "cdparanoia"
  depends_on "cdrdao"
  depends_on "ffmpeg"
  depends_on "mediainfo"
  depends_on "dvd+rw-tools"
  depends_on "id3lib"
  depends_on "id3v2"
  depends_on "cuetools"
  depends_on "mkvtoolnix"
  depends_on "opus-tools"
  depends_on "mjpegtools"
  depends_on "icoutils"
  depends_on "libdvdcss"
  depends_on "ffmpeg"
  depends_on "libdvdread"
  depends_on "libudfread"
  depends_on "expat"

  depends_on "ccextractor" => :recommended
  depends_on "sox" => :recommended
  depends_on "ddrescue" => :recommended
  # TODO depends_on "safecopy" => :recommended

  # TODO depends_on "lockfile-progs" vs "shlock"

  def install
    args = %W[]

    # on_macos do
    #   ...
    # end

    #depends_on "python-discid"
    system "pip3", "install", "discid"
    system "pip3", "install", "beautifulsoup4"
    system "pip3", "install", "lxml"

    system "touch", "#{prefix}/installed"

  end

end
