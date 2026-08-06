.PHONY: proto

PROTO_DIR := proto
GEN_DIR := gen

proto:
	@mkdir -p $(GEN_DIR)
	python -m grpc_tools.protoc \
		-I $(PROTO_DIR) \
		--python_out=$(GEN_DIR) \
		--grpc_python_out=$(GEN_DIR) \
		$(PROTO_DIR)/*.proto
	@echo "generated stubs in $(GEN_DIR)/"
.PHONY: venvs test

# One venv per service, each from its own requirements. A shared venv hid five
# missing-dependency bugs: code importing a package that was installed for a
# different service passes locally and fails in the image.
venvs:
	@for svc in orchestrator llm-gateway api-gateway workers; do \
		req="services/$$svc/requirements-dev.txt"; \
		[ -f "$$req" ] || req="services/$$svc/requirements.txt"; \
		echo "--- $$svc"; \
		python3 -m venv services/$$svc/.venv; \
		services/$$svc/.venv/bin/pip install -q -r $$req; \
	done

# Declared here rather than assumed from the shell. Tests were passing only
# because these happened to be exported in one terminal, which is the same
# class of bug as the shared venv: the environment I verify in is not the
# environment anyone else gets. Ports are the host-side mappings in
# docker-compose.yml; the suites skip themselves when nothing is listening.
TEST_ENV := \
	DATABASE_URL=postgresql+psycopg2://orchestrator:orchestrator@localhost:5432/orchestrator \
	REDIS_URL=redis://localhost:6379 \
	KAFKA_BOOTSTRAP_SERVERS=localhost:9092 \
	LLM_GATEWAY_GRPC=localhost:50052

test:
	@cd services/orchestrator && $(TEST_ENV) .venv/bin/python -m pytest -q
	@cd services/llm-gateway  && $(TEST_ENV) .venv/bin/python -m pytest -q
	@cd services/api-gateway  && $(TEST_ENV) .venv/bin/python -m pytest -q
