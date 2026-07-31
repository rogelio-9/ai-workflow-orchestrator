"""gRPC server for the LLM gateway."""

import logging
import os
import signal
import time
from concurrent import futures

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

import llm_gateway_pb2 as pb
import llm_gateway_pb2_grpc as pb_grpc

from app import providers, retry
from app.ratelimit import RateLimiter


LOG = logging.getLogger("llm_gateway")

GRPC_PORT = int(os.environ.get("GRPC_PORT", "50052"))

# Threads, not asyncio: provider calls are network-bound HTTP, so an async
# server buys nothing until we are CPU-bound, which a gateway never is.
MAX_WORKERS = int(os.environ.get("GRPC_MAX_WORKERS", "10"))

GRACE_PERIOD_SECONDS = 10

# Provider failures travel as gRPC status codes; the proto has no error field.
# The split that matters downstream is retryable vs not: UNAVAILABLE,
# DEADLINE_EXCEEDED and RESOURCE_EXHAUSTED are worth a backoff, the other two
# never succeed no matter how many attempts the worker spends on them.
_STATUS_FOR = {
    providers.UnknownProvider: grpc.StatusCode.INVALID_ARGUMENT,
    providers.ProviderNotFound: grpc.StatusCode.NOT_FOUND,
    providers.ProviderRejected: grpc.StatusCode.INVALID_ARGUMENT,
    providers.ProviderRateLimited: grpc.StatusCode.RESOURCE_EXHAUSTED,
    providers.ProviderTimeout: grpc.StatusCode.DEADLINE_EXCEEDED,
    providers.ProviderUnavailable: grpc.StatusCode.UNAVAILABLE,
}


class LLMGatewayServicer(pb_grpc.LLMGatewayServicer):
    def __init__(self, limiter=None):
        self._limiter = limiter if limiter is not None else RateLimiter()

    def RunCompletion(self, request, context):
        started = time.perf_counter()

        LOG.info(
            "completion requested run_id=%s step_id=%s model=%s",
            request.run_id,
            request.step_id,
            request.model,
        )

        try:
            provider, model = providers.resolve(request.model)
            name = request.model.partition(":")[0]

            def attempt():
                # Inside the retried operation so a rejected call re-checks
                # after the backoff, by which point the window has slid.
                if not self._limiter.admit(name):
                    raise providers.ProviderRateLimited(
                        f"{name} over its local quota "
                        f"({self._limiter.limit_for(name)}/window)"
                    )
                return provider.complete(
                    model, request.prompt, request.config, timeout=context.time_remaining()
                )

            result = retry.call_with_retry(attempt, time_remaining=context.time_remaining)
        except providers.ProviderError as exc:
            status = _STATUS_FOR.get(type(exc), grpc.StatusCode.INTERNAL)
            LOG.warning("completion failed model=%s %s", request.model, exc)
            context.abort(status, str(exc))

        latency_ms = int((time.perf_counter() - started) * 1000)
        LOG.info(
            "completion ok run_id=%s step_id=%s tokens=%d/%d latency_ms=%d",
            request.run_id,
            request.step_id,
            result.prompt_tokens,
            result.completion_tokens,
            latency_ms,
        )

        return pb.CompletionResponse(
            completion=result.text,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            latency_ms=latency_ms,
        )


def serve() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=MAX_WORKERS))
    pb_grpc.add_LLMGatewayServicer_to_server(LLMGatewayServicer(), server)

    # Standard grpc.health.v1 so compose can gate the worker on
    # `condition: service_healthy` instead of racing the listener.
    health_servicer = health.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
    health_servicer.set('', health_pb2.HealthCheckResponse.SERVING)
    health_servicer.set('llm_gateway.v1.LLMGateway', health_pb2.HealthCheckResponse.SERVING)
    server.add_insecure_port(f"[::]:{GRPC_PORT}")

    server.start()
    LOG.info("listening on %d (max_workers=%d)", GRPC_PORT, MAX_WORKERS)

    # Both signals take the same path so `docker stop` and Ctrl+C behave alike.
    def shutdown(signum, _frame):
        # Flip to NOT_SERVING before draining so a probe stops routing new
        # work here while in-flight RPCs finish.
        health_servicer.enter_graceful_shutdown()
        LOG.info("signal %d received, draining for %ds", signum, GRACE_PERIOD_SECONDS)
        server.stop(GRACE_PERIOD_SECONDS)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    server.wait_for_termination()
    LOG.info("stopped")


if __name__ == "__main__":
    serve()
