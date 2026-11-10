from types import SimpleNamespace

import pytest
from openai.types.chat import ChatCompletionMessage

from code_review.llm import Completion
from code_review.models import AgentResult, AgentReview, Finding, ReviewRequest, Role, SourceFile


@pytest.fixture
def request_snapshot():
    return ReviewRequest(title="Average order review", files=[SourceFile(
        path="orders.py", content="def average(values):\n    return sum(values) / len(values)\n",
    )])


@pytest.fixture
def finding():
    return Finding(
        title="Empty orders cause division by zero", severity="medium", file="orders.py",
        line_start=2, line_end=2, evidence="return sum(values) / len(values)",
        explanation="An empty list raises ZeroDivisionError.",
        recommendation="Define and handle the empty input case.",
        suggested_test="Assert the chosen behavior for an empty list.", confidence=0.99,
    )


class FakeLLM:
    settings = SimpleNamespace(model="nvidia/Nemotron-3_5-Lightning")

    def __init__(self, messages=None):
        self.messages = list(messages or [])
        self.calls = []

    def complete(self, messages, **kwargs):
        self.calls.append({"messages": list(messages), **kwargs})
        if self.messages:
            message = self.messages.pop(0)
            if isinstance(message, Exception):
                raise message
        else:
            message = ChatCompletionMessage(role="assistant", content='{"summary":"Source-validated review.","priority_ids":[],"next_steps":["Review findings."]}')
        return Completion(message=message, input_tokens=10, output_tokens=20)

    def close(self):
        pass


def successful_specialist(role: Role, request, llm):
    return AgentResult(role=role, status="completed", review=AgentReview(summary=f"{role.value} inspected."))
