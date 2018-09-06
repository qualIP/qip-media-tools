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

