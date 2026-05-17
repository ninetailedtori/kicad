.PHONY: help build lint fmt clean

SCRIPT = scripts/build.py

help: ## Show this help
	@grep -E '^[a-z-]+:.*##' Makefile | sed 's/:.*##/: /' | column -t -s:

build: ## Build catppuccin-kicad.zip
	uv run python $(SCRIPT)

lint: ## Lint build.py with autofix
	uv run ruff check $(SCRIPT) --fix
	uv run mypy $(SCRIPT)

fmt: ## Format repository
	uv run ruff format $(SCRIPT)
	uv run mdformat .
	uv run yamlfix .

clean: ## Remove build artifacts
	rm -f catppuccin-kicad.zip
	find . -type d -name __pycache__ -delete
	find . -type d -name .mypy_cache -delete
