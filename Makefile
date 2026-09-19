.PHONY: help install dev test lint demo run web doctor mcp clean

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

install:  ## Install runtime dependencies
	pip install -r requirements.txt && pip install -e .

dev:  ## Install dev + runtime dependencies
	pip install -r requirements-dev.txt && pip install -e .

test:  ## Run the test suite with coverage
	HELPDESK_OFFLINE=1 pytest --cov --cov-report=term-missing

lint:  ## Lint with ruff
	ruff check src tests main.py app.py

run:  ## Start an interactive CLI session
	python main.py

web:  ## Launch the Streamlit web UI
	streamlit run app.py

web-offline:  ## Launch the web UI without Ollama (fast, reproducible demo)
	HELPDESK_OFFLINE=1 streamlit run app.py

demo:  ## Run the scripted demo
	python main.py demo

doctor:  ## Check Ollama, knowledge base and database
	python main.py doctor

mcp:  ## Verify the MCP server over stdio
	python main.py mcp-check

clean:  ## Remove caches and the local database
	rm -rf .pytest_cache .ruff_cache .coverage htmlcov **/__pycache__ *.egg-info
	rm -f data/helpdesk.db
