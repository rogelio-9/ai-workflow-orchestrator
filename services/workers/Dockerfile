FROM python:3.12-slim

WORKDIR /app

# Root build context, same as the gateway: the generated stubs in gen/ are
# shared and belong to neither service. Requirements first so this layer caches.
COPY services/workers/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY gen/ ./gen/
COPY services/workers/ ./

# gen/ for the stubs, . for the worker's own sibling imports.
ENV PYTHONPATH=/app/gen:/app

CMD ["python", "base_worker.py"]
