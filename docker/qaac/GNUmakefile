.PHONY: latest

# http://www.andrews-corner.org/qaac.html
# https://sites.google.com/site/qaacpage/cabinet
# https://github.com/nu774/qaac

PACKAGE_NAMES = qaac-build qaac
PACKAGE_NAME = # TBD
QAAC_VER = 2.70
QAAC_VER_SHORT = 2.70
PACKAGE_VER = 2.70

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
	./preproc $(DEFINES) -I "../include" < "$<" > "$@"
	chmod a-w "$@"

%.png : %.gif
	ffmpeg -loglevel warning -hide_banner -i "$<" -frames:v 1 -y "$@"

FILE_QAAC_ZIP = qaac_$(QAAC_VER_SHORT).zip
$(FILE_QAAC_ZIP) :
	# https://github.com/nu774/qaac.git
	# https://sites.google.com/site/qaacpage/cabinet
	curl --output "$@" \
	    --location \
	    "https://github.com/nu774/qaac/releases/download/v$(QAAC_VER_SHORT)/qaac_$(QAAC_VER_SHORT).zip"

build-deps: $(FILE_QAAC_ZIP)

FILE_QAAC_MAKEPORTABLE2_ZIP = makeportable2.zip
$(FILE_QAAC_MAKEPORTABLE2_ZIP):
	# https://sites.google.com/site/qaacpage/cabinet
	curl --output "$@" \
	    --location \
	    "https://sites.google.com/site/qaacpage/cabinet/makeportable2.zip"

build-deps: $(FILE_QAAC_MAKEPORTABLE2_ZIP)

FILE_ITUNES64_SETUP = iTunes64Setup.exe
iTunes64Setup.exe:
	# https://www.apple.com/itunes/
	curl --output "$@" \
	    --location \
	    "https://www.apple.com/itunes/download/win64"

build-deps: $(FILE_ITUNES64_SETUP)

FILES_PREPROC += $(addprefix Dockerfile.,$(PACKAGE_NAMES))
build-deps: $(addprefix Dockerfile.,$(PACKAGE_NAMES))

.PHONY: build
build:
	./build

.PHONY: run
run:
	./qaac

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
	docker tag qualip/$(PACKAGE_NAME):$(PACKAGE_VER) qualip/$(PACKAGE_NAME):latest

.PHONY: push
push:
	$(if $(REGISTRY),,echo "REGISTRY environment variable missing" >&2 ; exit 1)
	docker tag qualip/$(PACKAGE_NAME):$(PACKAGE_VER) $(REGISTRY)/$(PACKAGE_NAME):$(PACKAGE_VER)
	docker push $(REGISTRY)/$(PACKAGE_NAME):$(PACKAGE_VER)

.PHONY: push-latest
push-latest: tag-latest
	$(if $(REGISTRY),,echo "REGISTRY environment variable missing" >&2 ; exit 1)
	docker tag qualip/$(PACKAGE_NAME):$(PACKAGE_VER) $(REGISTRY)/$(PACKAGE_NAME):latest
	docker push $(REGISTRY)/$(PACKAGE_NAME):latest

endif

XDG_DATA_DIRS0 = $(PREFIX)/share

.PHONY: install
install: install-deps
	d='$(PREFIX)/bin' ; test -d "$$d" || $(PREFIX_SUDO) mkdir -p "$$d"
	$(PREFIX_SUDO) install -m 755 qaac         "$(PREFIX)/bin/qaac"

.PHONY: uninstall
uninstall:
	$(PREFIX_SUDO) rm -fv "$(PREFIX)/bin/qaac"
	for p in $(PACKAGE_NAMES) ; do l=`docker image ls -q qualip/$$p | sort -u` ; if [ -n "$$l" ] ; then docker image rm --force $$l ; fi ; done

.PHONY: clean-all
clean-all: clean
clean-all: clean-dl

.PHONY: clean
clean:
	rm -fv $(FILES_PREPROC)
	for p in $(BUILD_PACKAGE_NAMES) ; do l=`docker image ls -q qualip/$$p | sort -u` ; if [ -n "$$l" ] ; then docker image rm --force $$l ; fi ; done

.PHONY: clean-dl
clean-dl:
	rm -fv $(FILE_QAAC_ZIP)
	rm -fv $(FILE_QAAC_MAKEPORTABLE2_ZIP)
	rm -fv $(FILE_ITUNES64_SETUP)

.PHONY: distclean
distclean: clean-all
