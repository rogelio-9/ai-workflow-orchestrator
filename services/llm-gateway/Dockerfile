FROM python:3.12-slim

WORKDIR /app

# Build context is the repo root: gen/ is shared with the workers and belongs
# to neither service. Requirements first so this layer caches.
COPY services/llm-gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY gen/ ./gen/
COPY services/llm-gateway/app/ ./app/

# _pb2_grpc imports its sibling with a bare top-level `import llm_gateway_pb2`,
# so gen/ has to be on the path in its own right.
ENV PYTHONPATH=/app/gen

EXPOSE 50052

# -m so app/ is imported as a package and `from app.providers import ...`
# resolves; running the file directly puts app/ itself on sys.path instead.
CMD ["python", "-m", "app.server"]
