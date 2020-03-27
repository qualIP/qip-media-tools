.PHONY: all
all:

.PHONY: install-pip3
install-pip3:
	sudo apt-get install python3-pip

.PHONY: install-audio-tools
install-audio-tools:
	sudo apt-get install ffmpeg

.PHONY: develop
develop:
	pip3 install --user --editable .

.PHONY: install-recommends
install-recommends:
	pip3 install --user -r recommends.txt

.PHONY: build-qip-tools-depends
build-qip-tools-depends: qip-tools-depends_1.0_all.deb
qip-tools-depends_1.0_all.deb: qip-tools-depends.ctl
	which equivs-build || sudo apt-get install equivs
	equivs-build $<

.PHONY: install-qip-tools-depends
install-qip-tools-depends: qip-tools-depends_1.0_all.deb
	sudo dpkg -i qip-tools-depends_1.0_all.deb || sudo apt-get --fix-broken install
