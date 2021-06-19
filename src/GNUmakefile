.PHONY: all
all:

DEPS_PACKAGE_VER=1.0

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
uninstall-user:
	pip3 uninstall qip

.PHONY: install-system
install-system: swig-targets
	$(maybe_sudo) pip3 install .

.PHONY: uninstall-system
uninstall-system:
	$(maybe_sudo) pip3 uninstall qip

.PHONY: develop
develop: swig-targets
	# pip3 install . --user --editable
	python3 setup.py develop --user
	#echo Execute: ln -s $(CURDIR)/qip ~/.local/lib/pythonX.X/site-packages/qip


FILE_DEPS_PACKAGE_DEB = qip-media-tools-depends_$(DEPS_PACKAGE_VER)_all.deb
$(FILE_DEPS_PACKAGE_DEB): qip-media-tools-depends.ctl
	which equivs-build || $(maybe_sudo) apt-get install equivs
	equivs-build $<

.PHONY: debian-build-qip-media-tools-depends
debian-build-qip-media-tools-depends: $(FILE_DEPS_PACKAGE_DEB)

.PHONY: debian-install-qip-media-tools-depends
debian-install-qip-media-tools-depends: $(FILE_DEPS_PACKAGE_DEB)
	$(maybe_sudo) dpkg -i $< || $(maybe_sudo) apt-get -y --fix-broken install

.PHONY: debian-uninstall-qip-media-tools-depends
debian-uninstall-qip-media-tools-depends:
	$(maybe_sudo) apt-get purge qip-media-tools-depends || true


FILE_DEPS_PACKAGE_ARCH = qip-media-tools-depends-$(DEPS_PACKAGE_VER)-1-any.pkg.tar.zst
$(FILE_DEPS_PACKAGE_ARCH): PKGBUILD.qip-media-tools-depends
	(which fakeroot && which strip) || $(maybe_sudo) pacman -S base-devel
	makepkg -fdp $<

.PHONY: arch-build-qip-media-tools-depends
arch-build-qip-media-tools-depends: $(FILE_DEPS_PACKAGE_ARCH)

.PHONY: arch-install-qip-media-tools-depends
arch-install-qip-media-tools-depends: $(FILE_DEPS_PACKAGE_ARCH)
	$(maybe_sudo) pacman -U $<

.PHONY: arch-uninstall-qip-media-tools-depends
arch-uninstall-qip-media-tools-depends:
	$(maybe_sudo) apt-get purge qip-media-tools-depends || true


.PHONY: brew-build-qip-media-tools-depends
brew-build-qip-media-tools-depends:
	# Nothing

.PHONY: brew-install-qip-media-tools-depends
brew-install-qip-media-tools-depends: qip-media-tools-depends.rb
	brew install --formulae ./$<

.PHONY: brew-uninstall-qip-media-tools-depends
brew-uninstall-qip-media-tools-depends:
	brew uninstall qip-media-tools-depends


.PHONY: build-qip-media-tools-depends
.PHONY: install-qip-media-tools-depends
.PHONY: uninstall-qip-media-tools-depends

ifneq ($(wildcard /etc/debian_version),)
PMS=apt-get
DISTRO=debian

build-qip-media-tools-depends: debian-build-qip-media-tools-depends
install-qip-media-tools-depends: debian-install-qip-media-tools-depends
uninstall-qip-media-tools-depends: debian-uninstall-qip-media-tools-depends

else
ifneq ($(wildcard /etc/arch-release),)
PMS=pacman
DISTRO=arch

build-qip-media-tools-depends: arch-build-qip-media-tools-depends
install-qip-media-tools-depends: arch-install-qip-media-tools-depends
uninstall-qip-media-tools-depends: arch-uninstall-qip-media-tools-depends

else
ifeq ($(shell uname -s),Darwin)
PMS=brew
DISTRO=darwin

build-qip-media-tools-depends: brew-build-qip-media-tools-depends
install-qip-media-tools-depends: brew-install-qip-media-tools-depends
uninstall-qip-media-tools-depends: brew-uninstall-qip-media-tools-depends

else

build-qip-media-tools-depends: unsupported-pms
install-qip-media-tools-depends: unsupported-pms
uninstall-qip-media-tools-depends: unsupported-pms

endif
endif
endif

unsupported-pms:
	@echo "ERROR: Unknown package management system." >&2
	@echo "Sorry, your system is not supported at this time." >&2
	exit 1

.PHONY: swig-targets
all: swig-targets
swig-targets: $(swig_targets)

.PHONY: clean-all
clean-all: clean
clean-all: clean-dl

.PHONY: clean
clean:
	rm -Rf build/
	rm -f qip-media-tools-depends_*.deb
	rm -f qip-media-tools-depends_*.buildinfo
	rm -f qip-media-tools-depends_*.changes
	rm -f qip-media-tools-depends-*.pkg.tar.zst

.PHONY: clean-dl
clean-dl:
	@true  # Nothing yet

.PHONY: distclean
distclean: clean-all
	rm -f $(swig_targets)
	rm -f qip/_*.cpython-*.so
