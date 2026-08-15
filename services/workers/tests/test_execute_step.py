"""The worker's pure decision logic: what runs, what fails, and what fans out.

No Kafka, Redis or Postgres here. These are the functions whose mistakes are
silent -- a step that is skipped rather than executed, or a dependent published
before its dependency finished -- so they are worth pinning independently of an
integration run that would hide the difference behind a green status.
"""

import pytest

from base_worker import TerminalStepError, execute_step, unblocked_steps

DIAMOND = {
    "nodes": [
        {"id": "fetch", "type": "tool_call"},
        {"id": "left", "type": "llm_call", "depends_on": ["fetch"]},
        {"id": "right", "type": "llm_call", "depends_on": ["fetch"]},
        {"id": "join", "type": "llm_call", "depends_on": ["left", "right"]},
    ]
}


def test_a_step_type_no_worker_owns_fails_terminally():
    with pytest.raises(TerminalStepError) as exc:
        execute_step({"node_id": "fetch", "step_type": "tool_call", "config": {}})
    # This used to return None, which the caller read as success: the step was
    # marked done and its dependents published, so a run could report COMPLETE
    # having never executed the step that produced the data.
    assert "tool_call" in str(exc.value)


def test_an_llm_call_with_no_model_fails_terminally_not_after_three_attempts():
    with pytest.raises(TerminalStepError):
        execute_step({"node_id": "a", "step_type": "llm_call", "config": {}})


def test_the_failure_injection_hook_still_raises():
    # Used by the integration tests to exercise the retry ladder, so it must
    # stay non-terminal -- a retryable failure, unlike the two above.
    import base_worker

    base_worker.FAIL_STEPS.add("boom")
    try:
        with pytest.raises(RuntimeError) as exc:
            execute_step({"node_id": "boom", "step_type": "llm_call", "config": {}})
        assert not isinstance(exc.value, TerminalStepError)
    finally:
        base_worker.FAIL_STEPS.discard("boom")


def ready(done: set[str]) -> list[str]:
    return [node["id"] for node in unblocked_steps(DIAMOND, done)]


def test_finishing_a_dependency_unblocks_both_of_its_dependents():
    assert ready({"fetch"}) == ["left", "right"]


def test_a_join_waits_for_every_dependency_not_the_first():
    # left is done but right is not, so join stays blocked. Publishing it here
    # would run the join against half its inputs.
    assert "join" not in ready({"fetch", "left"})


def test_a_fully_satisfied_node_is_unblocked_exactly_once():
    assert ready({"fetch", "left", "right"}) == ["join"]
    # Already done means already published; republishing would run it twice.
    assert ready({"fetch", "left", "right", "join"}) == []


def test_root_steps_are_never_republished():
    # The orchestrator publishes these at run creation. Including them here
    # would duplicate the first wave every time any step completed.
    assert ready(set()) == []
