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

test:
	@cd services/orchestrator && .venv/bin/python -m pytest -q
	@cd services/llm-gateway  && .venv/bin/python -m pytest -q
	@cd services/api-gateway  && .venv/bin/python -m pytest -q
