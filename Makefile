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