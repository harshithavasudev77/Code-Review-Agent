"""Validated contracts used by tools, specialists, the graph and exports."""

from __future__ import annotations

import hashlib
from enum import Enum
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Role(str, Enum):
    BUGS = "bugs"
    SECURITY = "security"
    TESTS = "tests"


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


SEVERITY_ORDER = {severity: i for i, severity in enumerate(Severity)}


class SourceFile(Contract):
    path: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1, max_length=80_000)

    @field_validator("path")
    @classmethod
    def safe_relative_path(cls, path: str) -> str:
        path = path.replace("\\", "/")
        p = PurePosixPath(path)
        if p.is_absolute() or ".." in p.parts or ":" in path or not p.name:
            raise ValueError("Use a relative source filename without parent traversal.")
        if any(ord(c) < 32 for c in path):
            raise ValueError("Source filenames cannot contain control characters.")
        return str(p)

    @property
    def line_count(self) -> int:
        return len(self.content.splitlines()) or 1

    @property
    def is_test(self) -> bool:
        p = PurePosixPath(self.path)
        return (
            p.name.startswith("test_")
            or p.stem.endswith(("_test", ".test", ".spec"))
            or any(part in {"tests", "__tests__", "test"} for part in p.parts[:-1])
        )

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content.encode()).hexdigest()


class ReviewRequest(Contract):
    title: str = Field(default="Code review", min_length=1, max_length=160)
    files: list[SourceFile] = Field(min_length=1, max_length=20)
    context: str = Field(default="", max_length=3000)
    origin: str = Field(default="User supplied source", max_length=500)

    @field_validator("files")
    @classmethod
    def validate_bundle(cls, files: list[SourceFile]) -> list[SourceFile]:
        if len({f.path for f in files}) != len(files):
            raise ValueError("Each source file must have a unique path.")
        if sum(len(f.content.encode()) for f in files) > 100_000:
            raise ValueError("Review at most 100 KB of source per run; split a larger change.")
        if any("\x00" in f.content for f in files):
            raise ValueError("Binary files are not supported.")
        return files


class Finding(Contract):
    title: str = Field(min_length=1, max_length=180)
    severity: Severity
    file: str = Field(min_length=1, max_length=240)
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    evidence: str = Field(default="", max_length=1200)
    explanation: str = Field(min_length=1, max_length=2200)
    recommendation: str = Field(min_length=1, max_length=1600)
    suggested_test: str = Field(default="", max_length=1600)
    confidence: float = Field(ge=0, le=1)
    category: str = Field(default="", max_length=100)


class AgentReview(Contract):
    summary: str = Field(min_length=1, max_length=2000)
    findings: list[Finding] = Field(default_factory=list, max_length=4)
    limitations: list[str] = Field(default_factory=list, max_length=8)


class AgentResult(Contract):
    role: Role
    status: Literal["completed", "failed"]
    review: AgentReview | None = None
    error: str = ""
    tool_calls: list[str] = Field(default_factory=list)
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    elapsed_seconds: float = 0


class RankedFinding(Finding):
    id: str
    agents: list[Role]


class Synthesis(Contract):
    summary: str = Field(min_length=1, max_length=2500)
    priority_ids: list[str] = Field(default_factory=list, max_length=24)
    next_steps: list[str] = Field(default_factory=list, max_length=8)


class TraceEvent(Contract):
    node: str
    message: str
    timestamp: str
    elapsed_seconds: float = 0


class ReviewReport(Contract):
    run_id: str
    title: str
    created_at: str
    model: str
    provider: str = "Nebius Token Factory"
    origin: str
    file_manifest: list[dict[str, str | int]]
    findings: list[RankedFinding]
    agents: list[AgentResult]
    summary: str
    next_steps: list[str]
    limitations: list[str]
    complete: bool
    human_review_required: bool = True
    decision: Literal["pending", "accepted", "changes_requested"] = "pending"
    reviewer_notes: str = ""
    elapsed_seconds: float
    input_tokens: int = 0
    output_tokens: int = 0
    llm_calls: int = 0


class HumanDecision(Contract):
    action: Literal["accepted", "changes_requested"]
    notes: str = Field(default="", max_length=2000)
