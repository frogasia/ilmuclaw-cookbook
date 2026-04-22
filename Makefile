.PHONY: help lint test test-help test-errors test-e2e run shell clean-state

help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n\nTargets:\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

lint: ## bash -n + shellcheck (if installed) against install.sh
	@bash -n install.sh && echo "bash -n: OK"
	@command -v shellcheck >/dev/null && shellcheck install.sh && echo "shellcheck: OK" || echo "shellcheck: not installed, skipped"

test: lint test-help test-errors ## Run everything that works without docker/openclaw

test-help: ## Verify --help renders and exits 0
	@./install.sh --help >/dev/null
	@echo "test-help: OK"

test-errors: ## Exercise each preflight failure and check its exit code
	@bash test/errors.sh

test-e2e: ## End-to-end against a containerised OpenClaw (state persists in test/.state/)
	docker compose -f test/docker-compose.yml run --rm cookbook-test

run: ## Apply cookbook config then keep gateway running (Ctrl-C to stop)
	docker compose -f test/docker-compose.yml run --rm --service-ports run

shell: ## Drop into a shell in the test container with the same state mounted
	docker compose -f test/docker-compose.yml run --rm --service-ports shell

clean-state: ## Remove the test harness state directory (test/.state/)
	rm -rf test/.state
