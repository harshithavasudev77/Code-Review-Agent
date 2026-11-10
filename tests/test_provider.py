from types import SimpleNamespace

import pytest
from openai import APIConnectionError, APIStatusError
from openai.types.chat import ChatCompletionMessage

from code_review.config import Settings
from code_review.llm import NebiusLLM, OutputError, ProviderError


def transport(sequence):
    llm = object.__new__(NebiusLLM)
    llm.settings = Settings(api_key="test-only")
    pending = iter(sequence)
    requests = []

    def create(**kwargs):
        requests.append(kwargs)
        result = next(pending)
        if isinstance(result, Exception):
            raise result
        return result

    llm.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return llm, requests


def response(finish="stop"):
    return SimpleNamespace(
        choices=[SimpleNamespace(finish_reason=finish, message=ChatCompletionMessage(role="assistant", content='{"ok":true}'))],
        usage=SimpleNamespace(prompt_tokens=100, completion_tokens=25),
    )


def status_error(code):
    return APIStatusError("body with fake-secret-do-not-display", response=SimpleNamespace(
        status_code=code, request=SimpleNamespace(), headers={},
    ), body={"private": "fake-secret-do-not-display"})


def test_connection_failure_has_bounded_attempts_and_sanitized_error(monkeypatch):
    monkeypatch.setattr("code_review.llm.time.sleep", lambda _: None)
    llm, calls = transport([APIConnectionError(request=SimpleNamespace()), APIConnectionError(request=SimpleNamespace())])
    with pytest.raises(ProviderError) as exc:
        llm.complete([])
    assert len(calls) == 2
    assert exc.value.attempts == 2
    assert "connection failed" in str(exc.value)


@pytest.mark.parametrize("code", [401, 403, 400])
def test_nonretryable_provider_errors_never_expose_response_body(code):
    llm, calls = transport([status_error(code)])
    with pytest.raises(ProviderError) as exc:
        llm.complete([])
    assert len(calls) == 1
    assert "fake-secret" not in str(exc.value)


def test_rate_limit_retries_and_lightning_direct_output_control(monkeypatch):
    monkeypatch.setattr("code_review.llm.time.sleep", lambda _: None)
    llm, calls = transport([status_error(429), response()])
    result = llm.complete([], json_mode=True)
    assert result.attempts == 2
    assert calls[-1]["extra_body"]["chat_template_kwargs"]["enable_thinking"] is False
    assert calls[-1]["model"] == "nvidia/Nemotron-3_5-Lightning"
    assert result.input_tokens == 100


def test_truncated_output_is_rejected_and_usage_is_retained():
    llm, calls = transport([response("length")])
    with pytest.raises(OutputError) as exc:
        llm.complete([])
    assert exc.value.input_tokens == 100
    assert exc.value.output_tokens == 25
    assert len(calls) == 1
