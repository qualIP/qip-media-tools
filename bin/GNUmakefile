.PHONY: all
all:

.PHONY: install install-%
install:

install: install-mkm4b
install-mkm4b: ~/bin/mkm4b
~/bin/mkm4b: mkm4b
	mkdir -p $(@D)
	ln -s "$(CURDIR)/$<" "$@"
