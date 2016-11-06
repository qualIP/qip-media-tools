.PHONY: all
all:

.PHONY: install install-%
install:

install: install-qaac
install-qaac: ~/bin/qaac
~/bin/qaac: qaac
	mkdir -p $(@D)
	ln -s "$(CURDIR)/$<" "$@"
