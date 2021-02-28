.PHONY: latest

PACKAGE_NAMES = wine64-build wine32-build wine64 wine32
PACKAGE_NAME = # TBD
WINE_TAG = wine-3.0.3
WINE_VER = 3.0.3
PACKAGE_VER = 3.0.3

REGISTRY = rip.jsoft.lan:5000

BUILD_PACKAGE_NAMES = $(filter %-build,$(PACKAGE_NAMES))
NONBUILD_PACKAGE_NAMES = $(filter-out %-build,$(PACKAGE_NAMES))

.PHONY: latest
latest: all
	$(MAKE) tag-latest

all:
all: build
all: install-deps

.DELETE_ON_ERROR:

.PHONY: build-deps
build-deps:

.PHONY: install-deps
install-deps:
	@# null

PREFIX ?= /usr/local
DEFINES =
DEFINES += -DPREFIX=$(PREFIX)
#DEFINES += -DDOCKERFILE_DEBUG

PREFIX_SUDO := $(shell [ -w "$(PREFIX)" ] || echo sudo)

FILES_PREPROC =
% : %.in
	rm -f "$@"
	gcc -E -iquote -traditional -undef $(DEFINES) -I "../include" - < "$<" | sed -e '/^#/ d' > "$@"
	chmod a-w "$@"

FILES_PREPROC += $(addprefix Dockerfile.,$(PACKAGE_NAMES))
build-deps: $(addprefix Dockerfile.,$(PACKAGE_NAMES))

.PHONY: wine-git-init
wine-git-init: wine-git/.git/config
wine-git/.git/config:
	git clone --no-checkout git://source.winehq.org/git/wine.git wine-git
build-deps: wine-git-init

.PHONY: wine-git-update-tag
wine-git-update-tag: wine-git-init
	git tag --verify $(WINE_TAG) || git fetch origin $(WINE_TAG)
build-deps: wine-git-init

.PHONY: build
build:
	./build

ifeq ($(PACKAGE_NAME),)

.PHONY: tag-latest push push-latest
tag-latest push push-latest:
	set -e ; \
	for PACKAGE_NAME in $(PACKAGE_NAMES) ; do \
	    make PACKAGE_NAME=$${PACKAGE_NAME} $@ ; \
	done

else

.PHONY: tag-latest
tag-latest:
	docker tag test/$(PACKAGE_NAME):$(PACKAGE_VER) test/$(PACKAGE_NAME):latest

.PHONY: push
push:
	docker tag test/$(PACKAGE_NAME):$(PACKAGE_VER) $(REGISTRY)/$(PACKAGE_NAME):$(PACKAGE_VER)
	docker push $(REGISTRY)/$(PACKAGE_NAME):$(PACKAGE_VER)

.PHONY: push-latest
push-latest: tag-latest
	docker tag test/$(PACKAGE_NAME):$(PACKAGE_VER) $(REGISTRY)/$(PACKAGE_NAME):latest
	docker push $(REGISTRY)/$(PACKAGE_NAME):latest

endif

XDG_DATA_DIRS0 = $(PREFIX)/share

.PHONY: install
install: install-deps
	echo "Nothing to install"

.PHONY: uninstall
uninstall:
	for p in $(PACKAGE_NAMES) ; do l=`docker image ls -q test/$$p | sort -u` ; if [ -n "$$l" ] ; then docker image rm --force $$l ; fi ; done

.PHONY: clean-all
clean-all: clean
clean-all: clean-dl

.PHONY: clean
clean:
	rm -fv $(FILES_PREPROC)
	for p in $(BUILD_PACKAGE_NAMES) ; do l=`docker image ls -q test/$$p | sort -u` ; if [ -n "$$l" ] ; then docker image rm --force $$l ; fi ; done

.PHONY: clean-dl
clean-dl:
	@# Nothing to do

.PHONY: distclean
distclean: clean-all
