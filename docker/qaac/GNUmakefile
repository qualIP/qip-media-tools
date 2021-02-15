.PHONY: latest

# http://www.andrews-corner.org/qaac.html
# https://sites.google.com/site/qaacpage/cabinet

PACKAGE_NAMES = qaac
PACKAGE_NAME = qaac
QAAC_VER = 2.70
QAAC_VER_SHORT = 2.70
PACKAGE_VER = 2.70

REGISTRY = rip.jsoft.lan:5000

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

PREFIX = /usr/local
DEFINES =
DEFINES += -DPREFIX=$(PREFIX)
#DEFINES += -DDOCKERFILE_DEBUG

FILES_PREPROC =
% : %.in
	rm -f "$@"
	gcc -E -iquote -traditional -undef $(DEFINES) -I "../include" - < "$<" | sed -e '/^#/ d' > "$@"
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
	echo "Please download $@ from https://www.apple.com/itunes/download/" >&2
	exit 1

build-deps: $(FILE_ITUNES64_SETUP)

FILES_PREPROC += Dockerfile
build-deps: Dockerfile

.PHONY: build
build:
	./build

.PHONY: run
run:
	./qaac

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

XDG_DATA_DIRS0 = $(PREFIX)/share

.PHONY: install
install: install-deps
	install -m 755 -D -T qaac         "$(PREFIX)/bin/qaac"

.PHONY: uninstall
uninstall:
	rm -fv "$(PREFIX)/bin/qaac"

.PHONY: clean-all
clean-all: clean
clean-all: clean-dl

.PHONY: clean
clean:
	rm -fv .*.timestamp
	rm -fv $(FILES_PREPROC)

.PHONY: clean-dl
clean-dl:
	rm -fv $(FILE_QAAC_ZIP)
	rm -fv $(FILE_QAAC_MAKEPORTABLE2_ZIP)
	rm -fv $(FILE_ITUNES64_SETUP)
