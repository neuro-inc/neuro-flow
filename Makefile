ISORT_DIRS := neuro_flow tests setup.py
BLACK_DIRS := $(ISORT_DIRS)
MYPY_DIRS :=  neuro_flow tests
FLAKE8_DIRS := $(ISORT_DIRS)
PYTEST_ARGS=

PYTEST_XDIST_NUM_THREADS ?= auto
COLOR ?= auto


.PHONY: lint
lint:
	isort --check-only --diff ${ISORT_DIRS}
	black --check $(BLACK_DIRS)
	mypy --show-error-codes --strict $(MYPY_DIRS)
	flake8 $(FLAKE8_DIRS)

.PHONY: publish-lint
publish-lint:
	twine check dist/*


.PHONY: fmt format
fmt format:
	isort $(ISORT_DIRS)
	black $(BLACK_DIRS)

.PHONY: clean
clean:
	find . -name '*.egg-info' -exec rm -rf {} +
	find . -name '__pycache__' -exec rm -rf {} +


.PHONY: test
test:
	pytest tests/unit


.PHONY: test-e2e
test-e2e:
	# E2E test are bound by IO, so it's OK to run a lot in parallel
	pytest -n 10 tests/e2e


.PHONY: build
build:
	docker build -t neuromation/neuro-flow:latest \
	    --build-arg NEURO_FLOW_VERSION="$(shell python setup.py --version)" \
	    .
