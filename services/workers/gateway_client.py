"""gRPC client for the LLM gateway.

The channel is built once at import: it holds connection state and a
background thread, so per-call construction would pay setup on every step and
defeat HTTP/2 connection reuse. Same reasoning as the Kafka producer singleton.
"""

import os

import grpc

import llm_gateway_pb2 as pb
import llm_gateway_pb2_grpc as pb_grpc

TARGET = os.environ.get("LLM_GATEWAY_GRPC", "localhost:50052")

# The deadline the worker gives the gateway. The gateway subtracts its own
# retry backoff from this rather than sleeping past it, so this value bounds
# the whole inner ladder -- see the gateway's retry module.
DEADLINE_SECONDS = float(os.environ.get("LLM_GATEWAY_DEADLINE_SECONDS", "120"))

_channel = grpc.insecure_channel(TARGET)
_stub = pb_grpc.LLMGatewayStub(_channel)


def run_completion(run_id: str, step_id: str, model: str, prompt: str, config: dict):
    """Call the gateway. gRPC status codes surface as grpc.RpcError."""
    generation = pb.GenerationConfig()
    # Only what the step actually set: leaving a field absent is how the
    # gateway tells "use the provider default" from an explicit zero.
    if "temperature" in config:
        generation.temperature = float(config["temperature"])
    if "max_tokens" in config:
        generation.max_tokens = int(config["max_tokens"])
    if "top_k" in config:
        generation.top_k = int(config["top_k"])
    if "top_p" in config:
        generation.top_p = float(config["top_p"])

    return _stub.RunCompletion(
        pb.CompletionRequest(
            run_id=run_id,
            step_id=step_id,
            prompt=prompt,
            model=model,
            config=generation,
        ),
        timeout=DEADLINE_SECONDS,
    )
