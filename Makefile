.PHONY: install publish build clean

install:
	uv tool install --editable .

build:
	uv build

publish: build
	uv publish

clean:
	rm -rf dist/
