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
	@cd frontend && npm test --silent

.PHONY: web token

# Not in docker-compose: the dev server wants fast reloads and a terminal, and
# containerising it buys nothing until there is something to deploy.
web:
	@cd frontend && npm run dev

# Mints a development JWT and writes it into frontend/.env.local.
#
# Writing the file rather than printing it: the token lives 12 hours, so this
# runs at the start of most sessions, and a copy-paste step that often is a
# step that eventually gets done wrong. JWT_SECRET is passed through the
# environment so it stays out of shell history.
#
# Still a token and not the signing key -- the frontend needs to call the
# gateway, not to mint identities. Override the owner with USER_ID=...
USER_ID ?= 11111111-1111-1111-1111-111111111111

token:
	@JWT_SECRET=$$(grep '^JWT_SECRET' .env | cut -d= -f2-) \
		services/api-gateway/.venv/bin/python scripts/mint_token.py $(USER_ID) \
		> /tmp/.wf_token
	@printf 'GATEWAY_URL=http://localhost:4000/graphql\nDEV_TOKEN=%s\n' \
		"$$(cat /tmp/.wf_token)" > frontend/.env.local
	@rm -f /tmp/.wf_token
	@echo "wrote frontend/.env.local for $(USER_ID) (valid 12h)"
	@echo "restart 'make web' to pick it up"
