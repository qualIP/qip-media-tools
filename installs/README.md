MakeMKV
=======

https://www.makemkv.com/forum/viewtopic.php?f=3&t=224

~~~~~~~~~~{.sh}
sudo apt-get install build-essential pkg-config libc6-dev libssl-dev libexpat1-dev libavcodec-dev libgl1-mesa-dev libqt4-dev zlib1g-dev ccextractor

wget http://www.makemkv.com/download/makemkv-oss-1.14.6.tar.gz
tar xzf makemkv-oss-1.14.6.tar.gz
cd makemkv-oss-1.14.6
./configure
make -j
sudo make install
cd ..

wget http://www.makemkv.com/download/makemkv-bin-1.14.6.tar.gz
tar xzf makemkv-bin-1.14.6.tar.gz
cd makemkv-bin-1.14.6
make
sudo make install
cd ..
~~~~~~~~~~



SubtitleEdit
============

https://www.nikse.dk/subtitleedit

http://www.sub-talk.net/topic/2751-subtitle-edit-for-ubuntu-troubleshoting-tips-and-tricks/

https://github.com/SubtitleEdit/subtitleedit/releases

~~~~~~~~~~{.sh}
sudo apt-get tesseract-ocr-eng tesseract-ocr-fra libtesseract-dev
winetricks vcrun2010
~~~~~~~~~~
