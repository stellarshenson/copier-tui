.PHONY: clean lint format requirements upgrade build install publish help test test-functional \
        create_environment remove_environment increment_version_number preflight screenshots

#################################################################################
# GLOBALS                                                                       #
#################################################################################

# running bare `make` prints the help screen
.DEFAULT_GOAL := help

PROJECT_DIR := $(shell dirname $(realpath $(lastword $(MAKEFILE_LIST))))
PROJECT_NAME = copier-tui
PYTHON_VERSION = 3.13
PYTHON_INTERPRETER = python

# the two distributable packages, published together and versioned in lockstep
PACKAGES = copier-ui copier-tui
UI_PYPROJECT = $(PROJECT_DIR)/packages/copier-ui/pyproject.toml
TUI_PYPROJECT = $(PROJECT_DIR)/packages/copier-tui/pyproject.toml

# Set SKIP_VERSION_INCREMENT=1 to skip auto-bumping the patch version in install/build
SKIP_VERSION_INCREMENT ?= 0

# throwaway environment used by the isolated functional tests
FUNCTIONAL_VENV = $(PROJECT_DIR)/tmp/functional-venv

#################################################################################
# STYLES                                                                        #
#################################################################################

MSG_PREFIX = \033[1m\033[36m>>>\033[0m
WARN_PREFIX = \033[33m>>>\033[0m
ERR_PREFIX = \033[31m>>>\033[0m
WARN_STYLE = \033[33m
ERR_STYLE = \033[31m
HIGHLIGHT_STYLE = \033[1m\033[94m
OK_STYLE = \033[92m
NO_STYLE = \033[0m

#################################################################################
# ENVIRONMENT CONFIGURATION                                                     #
#################################################################################

ENV_NAME = copier-tui
VENV_PATH = $(PROJECT_DIR)/.venv
UV_OPTS =

#################################################################################
# COMMANDS                                                                      #
#################################################################################

## Install workspace dependencies
.PHONY: requirements
requirements:
	@echo "$(MSG_PREFIX) installing workspace requirements with uv"
	uv $(UV_OPTS) sync --all-packages

## Upgrade dependencies to latest versions
.PHONY: upgrade
upgrade:
	@echo "$(MSG_PREFIX) upgrading packages with uv"
	uv $(UV_OPTS) sync --all-packages --upgrade

## Delete all compiled Python files, build output and scratch
clean:
	@echo "$(MSG_PREFIX) removing cache and compiled files"
	@find . -type f -name "*.py[co]" -delete
	@find . -type d -name '__pycache__' -exec rm -r {} +
	@find . -type d -name '*.egg-info' -exec rm -r {} +
	@find . -type d -name '.pytest_cache' -exec rm -r {} +
	@find . -type d -name '.ruff_cache' -exec rm -r {} +
	@echo "$(MSG_PREFIX) removing dist and build directories"
	@rm -rf build dist packages/*/dist packages/*/build
	@echo "$(MSG_PREFIX) removing logs and tmp directories"
	@rm -rf logs tmp

## Restore .env from encrypted .env.enc (or create empty)
.env:
	@if [ -f ".env.enc" ]; then \
		echo "$(MSG_PREFIX) decrypting .env.enc"; \
		openssl enc -d -aes-256-cbc -pbkdf2 -in .env.enc -out .env || { rm -f .env; echo "$(ERR_PREFIX) $(ERR_STYLE)decryption failed$(NO_STYLE)"; exit 1; }; \
	else \
		echo "$(MSG_PREFIX) creating empty .env"; \
		touch .env; \
	fi

## Encrypt .env to .env.enc (AES-256)
.env.enc: .env
	@echo "$(MSG_PREFIX) encrypting .env"
	@openssl enc -aes-256-cbc -pbkdf2 -in .env -out .env.enc
	@echo "$(OK_STYLE)>>> .env.enc file successfully created$(NO_STYLE)"

## Lint using ruff (use `make format` to do formatting)
lint:
	@echo "$(MSG_PREFIX) linting the sourcecode"
	uvx ruff format --check
	uvx ruff check

## Format source code with ruff
format:
	@echo "$(MSG_PREFIX) formatting the sourcecode"
	uvx ruff check --fix
	uvx ruff format

## Run unit tests
test:
	@echo "$(MSG_PREFIX) executing unit tests"
	uv $(UV_OPTS) run pytest --cov=copier_ui --cov=copier_tui -v ./tests/unit

## Run functional tests in a throwaway venv built from the wheels
test-functional: build
	@echo "$(MSG_PREFIX) creating throwaway environment at $(HIGHLIGHT_STYLE)$(FUNCTIONAL_VENV)$(NO_STYLE)"
	@rm -rf $(FUNCTIONAL_VENV)
	@uv $(UV_OPTS) venv -q --python $(PYTHON_VERSION) $(FUNCTIONAL_VENV)
	@echo "$(MSG_PREFIX) installing built wheels into the throwaway environment"
	@uv $(UV_OPTS) pip install -q --python $(FUNCTIONAL_VENV) \
		$(wildcard $(PROJECT_DIR)/packages/copier-ui/dist/*.whl) \
		$(wildcard $(PROJECT_DIR)/packages/copier-tui/dist/*.whl) \
		pytest pytest-asyncio
	@echo "$(MSG_PREFIX) executing functional tests against the installed wheels"
	$(FUNCTIONAL_VENV)/bin/pytest -v ./tests/functional
	@echo "$(OK_STYLE)>>> functional tests passed against the built wheels$(NO_STYLE)"

## Capture TUI screenshots into docs/assets (SVG)
screenshots:
	@echo "$(MSG_PREFIX) capturing TUI screenshots"
	uv $(UV_OPTS) run python -m copier_tui.screenshots

#################################################################################
# UV ENVIRONMENT MANAGEMENT                                                     #
#################################################################################

## Preflight check for required tools
preflight:
	@if ! command -v $(PYTHON_INTERPRETER) >/dev/null 2>&1; then \
		echo "$(ERR_PREFIX) $(ERR_STYLE)ERROR: $(PYTHON_INTERPRETER) not found$(NO_STYLE)"; \
		echo "$(ERR_PREFIX) $(ERR_STYLE)install Python from https://www.python.org/downloads/$(NO_STYLE)"; \
		exit 1; \
	fi

## Set up the uv virtual environment
create_environment: preflight
	@if [ -d "$(VENV_PATH)" ]; then \
		echo "$(MSG_PREFIX) virtual environment already exists at $(HIGHLIGHT_STYLE).venv$(NO_STYLE). Skipping creation."; \
	else \
		if ! command -v uv >/dev/null 2>&1; then \
			echo "$(MSG_PREFIX) installing uv"; \
			pip install -q uv; \
		fi; \
		echo "$(MSG_PREFIX) creating uv virtual environment"; \
		uv $(UV_OPTS) venv -q --python $(PYTHON_VERSION); \
		echo "$(MSG_PREFIX) new uv virtual environment created. Activate with:"; \
		echo "$(MSG_PREFIX) Unix/macOS: $(HIGHLIGHT_STYLE)source ./.venv/bin/activate$(NO_STYLE)"; \
	fi

## Remove previously created environment
remove_environment:
	@echo "$(MSG_PREFIX) removing uv virtual environment at $(HIGHLIGHT_STYLE).venv$(NO_STYLE)"
	@rm -rf $(VENV_PATH) $(FUNCTIONAL_VENV)
	@echo "$(OK_STYLE)>>> Environment removed$(NO_STYLE)"

## Install both packages in editable mode
install: create_environment increment_version_number requirements .env
	@echo "$(OK_STYLE)>>> $(PACKAGES) installed$(NO_STYLE)"

## Build wheels and sdists for both packages
build: clean install test
	@for pkg in $(PACKAGES); do \
		echo "$(MSG_PREFIX) building $(HIGHLIGHT_STYLE)$$pkg$(NO_STYLE)"; \
		uv $(UV_OPTS) build --package $$pkg --out-dir $(PROJECT_DIR)/packages/$$pkg/dist; \
	done
	@echo "$(OK_STYLE)>>> built $(words $(PACKAGES)) packages$(NO_STYLE)"

## Upload both packages to PyPI with twine (never runs on its own)
publish: build
	@echo "$(MSG_PREFIX) checking distributions with twine"
	@for pkg in $(PACKAGES); do \
		uv $(UV_OPTS) run twine check $(PROJECT_DIR)/packages/$$pkg/dist/*; \
	done
	@echo "$(WARN_PREFIX) $(WARN_STYLE)uploading $(words $(PACKAGES)) packages to PyPI$(NO_STYLE)"
	@echo "$(MSG_PREFIX) copier-ui goes first - copier-tui pins it exactly"
	uv $(UV_OPTS) run twine upload $(PROJECT_DIR)/packages/copier-ui/dist/*
	uv $(UV_OPTS) run twine upload $(PROJECT_DIR)/packages/copier-tui/dist/*
	@echo "$(OK_STYLE)>>> published $(PACKAGES)$(NO_STYLE)"

## Increment the shared patch version of both packages (skip with SKIP_VERSION_INCREMENT=1)
increment_version_number:
	@if [ "$(SKIP_VERSION_INCREMENT)" = "1" ]; then \
		echo "$(MSG_PREFIX) skipping version increment (SKIP_VERSION_INCREMENT=1)"; \
	else \
		$(PYTHON_INTERPRETER) $(PROJECT_DIR)/scripts/bump_version.py; \
	fi

#################################################################################
# Self Documenting Commands                                                     #
#################################################################################

.DEFAULT_GOAL := help

define PRINT_HELP_PYSCRIPT
import re, sys; \
lines = sys.stdin.read(); \
matches = re.findall(r'\n## ([^\n]+)\n(?!\.PHONY)([a-zA-Z_.][a-zA-Z0-9_.-]*):', lines); \
matches = sorted(matches, key=lambda x: x[1].lower()); \
print('\nAvailable rules:\n'); \
print('\n'.join(['\033[36m{:25}\033[0m{}'.format(*reversed(match)) for match in matches])); \
print()
endef
export PRINT_HELP_PYSCRIPT

## Print the list of available commands
help:
	@$(PYTHON_INTERPRETER) -c "$${PRINT_HELP_PYSCRIPT}" < $(MAKEFILE_LIST)

# EOF
