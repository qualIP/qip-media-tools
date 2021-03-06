.PHONY: latest

PACKAGE_NAMES = subtitleedit
PACKAGE_NAME = subtitleedit
# https://www.nikse.dk/subtitleedit/
SUBTITLEEDIT_VER = 3.6.1
SUBTITLEEDIT_VER_SHORT = $(subst .,,$(SUBTITLEEDIT_VER))
PACKAGE_VER = 3.6.1-qip1

BUILD_PACKAGE_NAMES = $(filter %-build,$(PACKAGE_NAMES))
NONBUILD_PACKAGE_NAMES = $(filter-out %-build,$(PACKAGE_NAMES))

.PHONY: latest
latest: all
	$(MAKE) tag-latest

all:
	# build must happen before install-deps!
	$(MAKE) build
	$(MAKE) install-deps

.DELETE_ON_ERROR:

.PHONY: build-deps
build-deps:

.PHONY: install-deps
install-deps:
	@# null

PREFIX ?= /usr/local
DEFINES =
DEFINES += -DPREFIX=$(PREFIX)
DEFINES += -DSUBTITLEEDIT_USE_WRAPPER
#DEFINES += -DDOCKERFILE_DEBUG

PREFIX_SUDO := $(shell [ -w "$(PREFIX)" ] || echo sudo)

FILES_PREPROC =
% : %.in
	rm -f "$@"
	./preproc $(DEFINES) -I "../include" < "$<" > "$@"
	chmod a-w "$@"

FILE_SUBTITLEEDIT_SETUP_ZIP = SubtitleEdit-$(SUBTITLEEDIT_VER)-Setup.zip
$(FILE_SUBTITLEEDIT_SETUP_ZIP) :
	# https://github.com/SubtitleEdit/subtitleedit/releases/download/3.5.16/SubtitleEdit-3.5.16-Setup.zip
	curl --output "$@" \
	    --location \
	    "https://github.com/SubtitleEdit/subtitleedit/releases/download/$(SUBTITLEEDIT_VER)/SubtitleEdit-$(SUBTITLEEDIT_VER)-Setup.zip"

#build-deps: $(FILE_SUBTITLEEDIT_SETUP_ZIP)

FILE_SUBTITLEEDIT_PORTABLE_ZIP = SE$(SUBTITLEEDIT_VER_SHORT).zip
$(FILE_SUBTITLEEDIT_PORTABLE_ZIP) :
	# https://github.com/SubtitleEdit/subtitleedit/releases/download/3.5.16/SE3516.zip
	curl --output "$@" \
	    --location \
	    "https://github.com/SubtitleEdit/subtitleedit/releases/download/$(SUBTITLEEDIT_VER)/SE$(SUBTITLEEDIT_VER_SHORT).zip"

build-deps: $(FILE_SUBTITLEEDIT_PORTABLE_ZIP)

.PHONY: subtitleedit-git-init
subtitleedit-git-init: subtitleedit-git/.git/config
subtitleedit-git/.git/config:
	git clone --no-checkout https://github.com/SubtitleEdit/subtitleedit.git subtitleedit-git
#build-deps: subtitleedit-git-init

FILES_PREPROC += Dockerfile
build-deps: Dockerfile

SubtitleEdit.ico:
	docker run --rm --entrypoint /bin/cat qualip/$(PACKAGE_NAME):$(PACKAGE_VER) "/home/developer/SubtitleEdit/SubtitleEdit.exe" < /dev/null > "temp-$@.exe"
	wrestool -x -t 14 "temp-$@.exe" > "$@"
	rm "temp-$@.exe"
	icotool -l "$@"

SubtitleEdit-48x48.ico: SubtitleEdit.ico
	icotool -x --width=48 --height=48 --bit-depth=32 -o "$@" "$<"

SubtitleEdit.png: SubtitleEdit-48x48.ico
	ffmpeg -loglevel warning -hide_banner -i "$<" -frames:v 1 -y "$@"

FILES_PREPROC += SubtitleEdit.desktop
all: SubtitleEdit.png
all: SubtitleEdit.desktop

.PHONY: build
build:
	./build

.PHONY: run
run:
	./SubtitleEdit --shell

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

XDG_DATA_DIRS0 = $(PREFIX)/share

.PHONY: install
install: install-deps
	d='$(PREFIX)/bin' ; test -d "$$d" || $(PREFIX_SUDO) mkdir -p "$$d"
	$(PREFIX_SUDO) install -m 755 SubtitleEdit         "$(PREFIX)/bin/SubtitleEdit"
	d='$(XDG_DATA_DIRS0)/applications' ; test -d "$$d" || $(PREFIX_SUDO) mkdir -p "$$d"
	$(PREFIX_SUDO) install -m 644 SubtitleEdit.desktop "$(XDG_DATA_DIRS0)/applications/SubtitleEdit.desktop"
	d='$(XDG_DATA_DIRS0)/icons' ; test -d "$$d" || $(PREFIX_SUDO) mkdir -p "$$d"
	$(PREFIX_SUDO) install -m 644 SubtitleEdit.png     "$(XDG_DATA_DIRS0)/icons/SubtitleEdit.png"
	if type update-desktop-database > /dev/null 2>&1 ; then \
	    $(PREFIX_SUDO) update-desktop-database "$(XDG_DATA_DIRS0)/applications" ; \
	fi

.PHONY: uninstall
uninstall:
	$(PREFIX_SUDO) rm -fv "$(PREFIX)/bin/SubtitleEdit"
	$(PREFIX_SUDO) rm -fv "$(XDG_DATA_DIRS0)/applications/SubtitleEdit.desktop"
	$(PREFIX_SUDO) rm -fv "$(XDG_DATA_DIRS0)/icons/SubtitleEdit.png"
	for p in $(PACKAGE_NAMES) ; do l=`docker image ls -q qualip/$$p | sort -u` ; if [ -n "$$l" ] ; then docker image rm --force $$l ; fi ; done

.PHONY: clean-all
clean-all: clean
clean-all: clean-dl

.PHONY: clean
clean:
	rm -fv $(FILES_PREPROC)
	rm -fv temp-*.exe
	rm -fv SubtitleEdit*.ico
	rm -fv SubtitleEdit.png
	for p in $(BUILD_PACKAGE_NAMES) ; do l=`docker image ls -q qualip/$$p | sort -u` ; if [ -n "$$l" ] ; then docker image rm --force $$l ; fi ; done

.PHONY: clean-dl
clean-dl:
	rm -fv $(FILE_SUBTITLEEDIT_SETUP_ZIP)
	rm -fv $(FILE_SUBTITLEEDIT_PORTABLE_ZIP)

.PHONY: distclean
distclean: clean-all
