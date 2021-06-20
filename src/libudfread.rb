class Libudfread < Formula
  desc "UDF reader"
  homepage "https://code.videolan.org/videolan/libudfread"
  url "https://code.videolan.org/videolan/libudfread/-/archive/1.1.1/libudfread-1.1.1.tar.bz2"
  license "GPL-2.1"
  version "1.1.1"

  head do
    url "https://code.videolan.org/videolan/libudfread.git"
  end

  depends_on "autoconf" => :build
  depends_on "automake" => :build
  depends_on "libtool" => :build

  # depends_on "libdvdcss"

  def install
    # ENV.append "CFLAGS", "-DHAVE_DVDCSS_DVDCSS_H"
    # ENV.append "LDFLAGS", "-ldvdcss"

    system "./bootstrap"
    system "./configure", "--prefix=#{prefix}"
    system "make", "install"
  end
end
