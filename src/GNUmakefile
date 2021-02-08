.PHONY: all
all:

.PHONY: install-pip3
install-pip3:
	sudo apt-get install python3-pip

swig_targets =

qip/libdvdread_swig_wrap.c qip/libdvdread_swig.py: qip/libdvdread_swig.i
	swig -Wall -I/usr/include -python -py3 $<
swig_targets += qip/libdvdread_swig_wrap.c qip/libdvdread_swig.py

qip/libudfread_swig_wrap.c qip/libudfread_swig.py: qip/libudfread_swig.i
	swig -Wall -I/usr/include -python -py3 $<
swig_targets += qip/libudfread_swig_wrap.c qip/libudfread_swig.py

.PHONY: install-read-only
install-read-only: swig-targets
	pip3 install . --user

.PHONY: develop
develop: swig-targets
	# pip3 install . --user --editable
	python3 setup.py develop --user
	echo Execute: ln -s $(CURDIR)/qip ~/.local/lib/pythonX.X/site-packages/qip

.PHONY: build-qip-tools-depends
build-qip-tools-depends: qip-tools-depends_1.0_all.deb
qip-tools-depends_1.0_all.deb: qip-tools-depends.ctl
	which equivs-build || sudo apt-get install equivs
	equivs-build $<

.PHONY: install-qip-tools-depends
install-qip-tools-depends: qip-tools-depends_1.0_all.deb
	sudo dpkg -i qip-tools-depends_1.0_all.deb || sudo apt-get --fix-broken install

.PHONY: swig-targets
all: swig-targets
swig-targets: $(swig_targets)

clean:
	rm -f $(swig_targets)
	rm -f qip/_*.cpython-*.so
