"""OpenAI-format Nebius transport, bounded retries, and validated JSON output."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, TypeVar

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI
from pydantic import BaseModel, ValidationError

from .config import NEBIUS_BASE_URL, Settings

T = TypeVar("T", bound=BaseModel)


class ProviderError(RuntimeError):
    """Sanitized provider failure; never embed a response body or credential."""

    def __init__(self, message: str, *, attempts: int = 1):
        super().__init__(message)
        self.attempts = attempts


class OutputError(ValueError):
    """Invalid model output after a bounded repair attempt."""

    def __init__(self, message: str, *, input_tokens: int = 0, output_tokens: int = 0,
                 attempts: int = 1):
        super().__init__(message)
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.attempts = attempts


@dataclass
class Completion:
    message: Any
    input_tokens: int = 0
    output_tokens: int = 0
    attempts: int = 1


def parse_json(content: str, schema: type[T]) -> T:
    content = content.strip()
    content = re.sub(r"^```(?:json)?\s*", "", content)
    content = re.sub(r"\s*```$", "", content)
    try:
        return schema.model_validate_json(content)
    except ValidationError as exc:
        fields = "; ".join(
            ".".join(str(part) for part in e["loc"]) + ": " + e["type"]
            for e in exc.errors()[:8]
        )
        raise OutputError("Model response did not match the required review schema. " + fields) from None
    except ValueError:
        raise OutputError("Model response was not valid JSON.") from None


def schema_instruction(schema: type[BaseModel]) -> str:
    return "Return only a JSON object matching this JSON Schema:\n" + json.dumps(schema.model_json_schema())


class NebiusLLM:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = OpenAI(
            base_url=NEBIUS_BASE_URL,
            api_key=settings.api_key.get_secret_value(),
            timeout=settings.timeout_seconds,
            max_retries=0,
        )

    def complete(self, messages: list[dict], *, tools: list[dict] | None = None,
                 tool_choice: Any = None, json_mode: bool = False,
                 output_schema: type[BaseModel] | dict | None = None) -> Completion:
        kwargs: dict[str, Any] = {}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice or "auto"
            kwargs["parallel_tool_calls"] = False
        if output_schema:
            schema = output_schema if isinstance(output_schema, dict) else output_schema.model_json_schema()
            name = schema.get("title", "ReviewOutput")
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": name, "schema": schema},
            }
        elif json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if self.settings.model == "nvidia/Nemotron-3_5-Lightning":
            # NVIDIA's documented direct-output control: preserve the budget for tool/JSON output.
            kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
        for attempt in range(1, self.settings.max_attempts + 1):
            try:
                response = self.client.chat.completions.create(
                    model=self.settings.model, messages=messages,
                    temperature=0.1, max_tokens=self.settings.max_tokens, **kwargs,
                )
                if not response.choices:
                    raise OutputError("Provider returned no completion choices.")
                choice = response.choices[0]
                usage = response.usage
                if choice.finish_reason == "length":
                    raise OutputError(
                        "Model output reached the token limit; reduce the review scope.",
                        input_tokens=usage.prompt_tokens if usage else 0,
                        output_tokens=usage.completion_tokens if usage else 0, attempts=attempt,
                    )
                return Completion(
                    message=choice.message,
                    input_tokens=usage.prompt_tokens if usage else 0,
                    output_tokens=usage.completion_tokens if usage else 0,
                    attempts=attempt,
                )
            except (APIConnectionError, APITimeoutError):
                error = "Nebius connection failed or timed out. Check connectivity and retry."
            except APIStatusError as exc:
                status = exc.status_code
                if status in {401, 403}:
                    raise ProviderError("Nebius rejected the credential or model access.") from None
                if status == 404:
                    raise ProviderError("The configured model is unavailable at the Nebius endpoint.") from None
                if status != 429 and status < 500:
                    raise ProviderError(f"Nebius rejected the request (HTTP {status}).") from None
                error = f"Nebius is temporarily unavailable (HTTP {status}); retry later."
            if attempt < self.settings.max_attempts:
                time.sleep(min(attempt, 2))
        raise ProviderError(error, attempts=self.settings.max_attempts) from None

    def close(self) -> None:
        self.client.close()
