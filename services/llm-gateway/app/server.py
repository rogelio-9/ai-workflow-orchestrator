"""gRPC server for the LLM gateway.

RunCompletion returns a hardcoded completion. The provider factory lands
behind this same RPC signature, so callers do not change.
"""

import logging
import os
import signal
import time
from concurrent import futures

import grpc

import llm_gateway_pb2 as pb
import llm_gateway_pb2_grpc as pb_grpc


LOG = logging.getLogger("llm_gateway")

GRPC_PORT = int(os.environ.get("GRPC_PORT", "50052"))

# Threads, not asyncio: provider calls are network-bound HTTP, so an async
# server buys nothing until we are CPU-bound, which a gateway never is.
MAX_WORKERS = int(os.environ.get("GRPC_MAX_WORKERS", "10"))

GRACE_PERIOD_SECONDS = 10


class LLMGatewayServicer(pb_grpc.LLMGatewayServicer):
    def RunCompletion(self, request, context):
        started = time.perf_counter()

        LOG.info(
            "completion requested run_id=%s step_id=%s model=%s",
            request.run_id,
            request.step_id,
            request.model,
        )

        # TODO(provider): replaced by the provider factory.
        completion = f"[stub completion for model={request.model!r}]"

        latency_ms = int((time.perf_counter() - started) * 1000)

        # TODO(provider): ~4 chars/token stand-in so the field is non-zero
        # end-to-end. Real providers report real counts.
        return pb.CompletionResponse(
            completion=completion,
            prompt_tokens=len(request.prompt) // 4,
            completion_tokens=len(completion) // 4,
            latency_ms=latency_ms,
        )


def serve() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=MAX_WORKERS))
    pb_grpc.add_LLMGatewayServicer_to_server(LLMGatewayServicer(), server)
    server.add_insecure_port(f"[::]:{GRPC_PORT}")

    server.start()
    LOG.info("listening on %d (max_workers=%d)", GRPC_PORT, MAX_WORKERS)

    # Both signals take the same path so `docker stop` and Ctrl+C behave alike.
    def shutdown(signum, _frame):
        LOG.info("signal %d received, draining for %ds", signum, GRACE_PERIOD_SECONDS)
        server.stop(GRACE_PERIOD_SECONDS)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    server.wait_for_termination()
    LOG.info("stopped")


if __name__ == "__main__":
    serve()
