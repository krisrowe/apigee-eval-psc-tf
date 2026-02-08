.PHONY: setup test install clean

VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

setup:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip --index-url https://pypi.org/simple
	$(PIP) install -e .[dev] --index-url https://pypi.org/simple

test: setup
	$(VENV)/bin/pytest tests/

install:
	cd . && pipx install -e . --force --pip-args="--index-url https://pypi.org/simple"

clean:
	rm -rf $(VENV)
	rm -rf build dist *.egg-info
	find . -name "__pycache__" -exec rm -rf {} +
