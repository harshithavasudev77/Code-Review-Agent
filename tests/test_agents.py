import json

import pytest
from openai.types.chat import ChatCompletionMessage

from code_review.agents import run_specialist, validate_evidence
from code_review.llm import OutputError, ProviderError
from code_review.models import AgentReview, Role
from conftest import FakeLLM


def tool_message(name="inspect_sources", arguments="{}"):
    return ChatCompletionMessage(role="assistant", content=None, tool_calls=[{
        "id": "call_1", "type": "function", "function": {"name": name, "arguments": arguments},
    }])


def review_message(finding):
    return ChatCompletionMessage(role="assistant", content=AgentReview(summary="Found an empty input defect.", findings=[finding]).model_dump_json())


def test_specialist_uses_real_source_tool_before_review(request_snapshot, finding):
    llm = FakeLLM([tool_message(), review_message(finding)])
    result = run_specialist(Role.BUGS, request_snapshot, llm)
    assert result.status == "completed"
    assert result.tool_calls == ["inspect_sources"]
    assert result.llm_calls == 2
    tool_output = next(m for m in llm.calls[1]["messages"] if m["role"] == "tool")
    assert tool_output["role"] == "tool"
    assert json.loads(tool_output["content"])["files"][0]["source"].startswith("1: def average")


def test_invalid_line_reference_is_repaired_once(request_snapshot, finding):
    invalid = finding.model_copy(update={"line_start": 99, "line_end": 99})
    llm = FakeLLM([tool_message(), review_message(invalid), review_message(finding)])
    result = run_specialist(Role.BUGS, request_snapshot, llm)
    assert result.status == "completed"
    assert len(llm.calls) == 3
    assert llm.calls[-1]["json_mode"] is True
    assert llm.calls[-1]["output_schema"]["$defs"]["Finding"]["properties"]["file"]["enum"] == ["orders.py"]


def test_unrepairable_citation_fails_agent(request_snapshot, finding):
    invalid = finding.model_copy(update={"file": "not-submitted.py"})
    result = run_specialist(Role.SECURITY, request_snapshot, FakeLLM([
        tool_message(), review_message(invalid), review_message(invalid),
    ]))
    assert result.status == "failed"
    assert result.review is None
    assert "outside" in result.error


def test_agent_cannot_skip_source_inspection(request_snapshot, finding):
    result = run_specialist(Role.BUGS, request_snapshot, FakeLLM([review_message(finding)]))
    assert result.status == "failed"
    assert "inspect" in result.error


def test_provider_failure_returns_explicit_status(request_snapshot):
    result = run_specialist(Role.SECURITY, request_snapshot, FakeLLM([ProviderError("Nebius connection failed.")]))
    assert result.status == "failed"
    assert result.error == "Nebius connection failed."


def test_test_agent_never_claims_measured_coverage(request_snapshot, finding):
    result = run_specialist(Role.TESTS, request_snapshot, FakeLLM([tool_message(), review_message(finding)]))
    assert any("Coverage was not measured" in s for s in result.review.limitations)


def test_model_quotes_are_replaced_by_original_source(request_snapshot, finding):
    draft = finding.model_copy(update={"evidence": "return invented_source()"})
    validated = validate_evidence(AgentReview(summary="Review", findings=[draft]), request_snapshot)
    assert validated.findings[0].evidence == "    return sum(values) / len(values)"


@pytest.mark.parametrize("change", [{"line_start": 99, "line_end": 99}, {"line_start": 2, "line_end": 1}])
def test_source_validation_rejects_wrong_ranges_and_quotes(request_snapshot, finding, change):
    with pytest.raises(OutputError):
        validate_evidence(AgentReview(summary="Review", findings=[finding.model_copy(update=change)]), request_snapshot)
