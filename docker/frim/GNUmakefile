.PHONY: latest

PACKAGE_NAMES = frim
PACKAGE_NAME = frim
# https://www.videohelp.com/software/FRIM
FRIM_VER = 1.31
PACKAGE_VER = 1.31

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

FILE_FRIM_ZIP = FRIM_x64_version_$(FRIM_VER).zip
$(FILE_FRIM_ZIP) :
	# https://www.videohelp.com/software/FRIM
	curl --output "$@" \
	    --location \
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
	docker tag test/$(PACKAGE_NAME):$(PACKAGE_VER) $(REGISTRY)/$(PACKAGE_NAME):$(PACKAGE_VER)
	docker push $(REGISTRY)/$(PACKAGE_NAME):$(PACKAGE_VER)

.PHONY: push-latest
push-latest: tag-latest
	docker tag test/$(PACKAGE_NAME):$(PACKAGE_VER) $(REGISTRY)/$(PACKAGE_NAME):latest
	docker push $(REGISTRY)/$(PACKAGE_NAME):latest

XDG_DATA_DIRS0 = $(PREFIX)/share

.PHONY: install
install: install-deps
	install -m 755 -D -T FRIMDecode         "$(PREFIX)/bin/FRIMDecode"
	install -m 755 -D -T FRIMEncode         "$(PREFIX)/bin/FRIMEncode"
	install -m 755 -D -T FRIMTranscode      "$(PREFIX)/bin/FRIMTranscode"

.PHONY: uninstall
uninstall:
	rm -fv "$(PREFIX)/bin/FRIMDecode"
	rm -fv "$(PREFIX)/bin/FRIMEncode"
	rm -fv "$(PREFIX)/bin/FRIMTranscode"

.PHONY: clean-all
clean-all: clean
clean-all: clean-dl

.PHONY: clean
clean:
	rm -fv .*.timestamp
	rm -fv $(FILES_PREPROC)

.PHONY: clean-dl
clean-dl:
	true  # Nothing yet
	#rm -fv $(FILE_FRIM_ZIP)
