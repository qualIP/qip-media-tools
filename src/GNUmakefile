.PHONY: all
all:

maybe_sudo=$(if $(filter $(USER),root),,sudo)

swig_targets =

qip/libdvdread_swig_wrap.c qip/libdvdread_swig.py: qip/libdvdread_swig.i
	swig -Wall -I/usr/include -python -py3 $<
swig_targets += qip/libdvdread_swig_wrap.c qip/libdvdread_swig.py

qip/libudfread_swig_wrap.c qip/libudfread_swig.py: qip/libudfread_swig.i
	swig -Wall -I/usr/include -python -py3 $<
swig_targets += qip/libudfread_swig_wrap.c qip/libudfread_swig.py

.PHONY: install-user
install-user: swig-targets
	pip3 install . --user

.PHONY: uninstall-user
uninstall-user: swig-targets
	pip3 uninstall . --user

.PHONY: install-system
install-system: swig-targets
	$(maybe_sudo) pip3 install . --system

.PHONY: uninstall-system
uninstall-system:
	$(maybe_sudo) pip3 uninstall . --system

.PHONY: develop
develop: swig-targets
	# pip3 install . --user --editable
	python3 setup.py develop --user
	#echo Execute: ln -s $(CURDIR)/qip ~/.local/lib/pythonX.X/site-packages/qip

.PHONY: build-qip-tools-depends
build-qip-tools-depends: qip-tools-depends_1.0_all.deb
qip-tools-depends_1.0_all.deb: qip-tools-depends.ctl
	which equivs-build || $(maybe_sudo) apt-get install equivs
	equivs-build $<

.PHONY: install-qip-tools-depends
install-qip-tools-depends: qip-tools-depends_1.0_all.deb
	$(maybe_sudo) dpkg -i qip-tools-depends_1.0_all.deb || $(maybe_sudo) apt-get --fix-broken install

.PHONY: uninstall-qip-tools-depends
uninstall-qip-tools-depends:
	$(maybe_sudo) apt-get purge qip-tools-depends_1.0_all.deb || true

.PHONY: swig-targets
all: swig-targets
swig-targets: $(swig_targets)

clean:
	rm -f $(swig_targets)
	rm -f qip/_*.cpython-*.so
