.PHONY: build clean publish pyenv tests tox

SHELL := $(shell bash -c 'command -v bash')
msg := fix: first
export msg

build:
	@eval "$$(pyenv init --path)"; python3.8 -m pip install --quiet build && \
python3.8 -m build --wheel -o $$(mktemp -d) && rm -rf build dist
	@eval "$$(pyenv init --path)"; python3.9 -m pip install --quiet build && \
python3.9 -m build --wheel -o $$(mktemp -d) && rm -rf build dist
	@python3.10 -m build --wheel -o $$(mktemp -d) && rm -rf build dist
	@eval "$$(pyenv init --path)"; python3.11 -m pip install --quiet build && \
python3.11 -m build --wheel -o $$(mktemp -d) && rm -rf build dist

clean:
	@rm -rf build dist

publish: tox build clean
	@git add .
	@git commit --quiet -a -m "$${msg:-auto}" || true
	@git push --quiet

pyenv:
	@pyenv install 3.8.13
	@pyenv install 3.9.11
	@pyenv install 3.11-dev
	@pyenv global 3.8.13 3.9.11 3.11-dev

tests:
	@pytest

tox:
	@eval "$$(pyenv init --path)"; tox

