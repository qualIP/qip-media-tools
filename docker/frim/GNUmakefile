.PHONY: latest

PACKAGE_NAMES = frim
PACKAGE_NAME = frim
# https://www.videohelp.com/software/FRIM
FRIM_VER = 1.31
PACKAGE_VER = 1.31

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

%.png : %.gif
	ffmpeg -loglevel warning -hide_banner -i "$<" -frames:v 1 -y "$@"

FILE_FRIM_ZIP = FRIM_x64_version_$(FRIM_VER).zip
$(FILE_FRIM_ZIP) :
	# https://www.videohelp.com/software/FRIM#download
	curl --output "$@" \
	    --location \
	    --referer "https://www.videohelp.com/software/FRIM" \
	    "https://www.videohelp.com/download/FRIM_x64_version_$(FRIM_VER).zip"

build-deps: $(FILE_FRIM_ZIP)

FILES_PREPROC += Dockerfile
build-deps: Dockerfile

.PHONY: build
build:
	./build

.PHONY: run
run:
	./FRIM --shell

.PHONY: tag-latest
tag-latest:
	docker tag test/$(PACKAGE_NAME):$(PACKAGE_VER) test/$(PACKAGE_NAME):latest

.PHONY: push
push:
	$(if $(REGISTRY),,echo "REGISTRY environment variable missing" >&2 ; exit 1)
	docker tag test/$(PACKAGE_NAME):$(PACKAGE_VER) $(REGISTRY)/$(PACKAGE_NAME):$(PACKAGE_VER)
	docker push $(REGISTRY)/$(PACKAGE_NAME):$(PACKAGE_VER)

.PHONY: push-latest
push-latest: tag-latest
	$(if $(REGISTRY),,echo "REGISTRY environment variable missing" >&2 ; exit 1)
	docker tag test/$(PACKAGE_NAME):$(PACKAGE_VER) $(REGISTRY)/$(PACKAGE_NAME):latest
	docker push $(REGISTRY)/$(PACKAGE_NAME):latest

XDG_DATA_DIRS0 = $(PREFIX)/share

.PHONY: install
install: install-deps
	$(PREFIX_SUDO) install -m 755 -D -T FRIMDecode         "$(PREFIX)/bin/FRIMDecode"
	$(PREFIX_SUDO) install -m 755 -D -T FRIMEncode         "$(PREFIX)/bin/FRIMEncode"
	$(PREFIX_SUDO) install -m 755 -D -T FRIMTranscode      "$(PREFIX)/bin/FRIMTranscode"

.PHONY: uninstall
uninstall:
	$(PREFIX_SUDO) rm -fv "$(PREFIX)/bin/FRIMDecode"
	$(PREFIX_SUDO) rm -fv "$(PREFIX)/bin/FRIMEncode"
	$(PREFIX_SUDO) rm -fv "$(PREFIX)/bin/FRIMTranscode"
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
	rm -fv $(FILE_FRIM_ZIP)

.PHONY: distclean
distclean: clean-all
