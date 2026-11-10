import json

import pytest
from pydantic import ValidationError

from code_review.config import ConfigurationError, load_settings
from code_review.models import ReviewRequest, SourceFile
from code_review.samples import load_sample, sample_catalog
from code_review.tools import build_tools, python_analysis, test_inventory as inspect_test_inventory


def test_unsafe_source_paths_and_duplicate_paths_are_rejected():
    for path in ["../secret.py", "/etc/passwd", "C:\\secrets.py", "a\n.py"]:
        with pytest.raises(ValidationError):
            SourceFile(path=path, content="x=1")
    with pytest.raises(ValidationError):
        ReviewRequest(files=[SourceFile(path="a.py", content="x=1")] * 2)


def test_source_byte_budget_and_binary_input_are_rejected():
    with pytest.raises(ValidationError):
        ReviewRequest(files=[SourceFile(path="a.py", content="é" * 60_000)])
    with pytest.raises(ValidationError):
        ReviewRequest(files=[SourceFile(path="a.py", content="\x00")])


def test_tools_only_read_snapshot_and_never_execute(tmp_path):
    marker = tmp_path / "executed"
    source = SourceFile(path="untrusted.py", content=f"from pathlib import Path\nPath({str(marker)!r}).touch()\n")
    tools = build_tools(ReviewRequest(files=[source]))
    tools["inspect_sources"].invoke({})
    assert not marker.exists()
    assert "error" in json.loads(tools["read_lines"].invoke({"path": "../secrets", "start_line": 1, "end_line": 2}))


def test_static_analysis_handles_aliases_syntax_errors_and_test_inventory():
    code = SourceFile(path="service.py", content="import subprocess as sp\ndef run(x, items=[]):\n    return sp.run(x, shell=True)\n")
    data = python_analysis([code])["files"][0]
    assert {o["kind"] for o in data["observations"]} == {"mutable_default", "shell_execution"}
    broken = python_analysis([SourceFile(path="broken.py", content="def broken(:")])
    assert broken["files"][0]["parse_error"]["kind"] == "SyntaxError"
    inventory = inspect_test_inventory([code, SourceFile(path="tests/test_service.py", content="def test_run():\n    pass\n")])
    assert inventory["coverage_measured"] is False
    assert inventory["test_files"][0]["tests"] == ["test_run"]


def test_credentials_precedence_and_secret_exclusion(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("NEBIUS_API_KEY=dotenv-secret\n")
    monkeypatch.setenv("NEBIUS_API_KEY", "environment-secret")
    settings = load_settings(tmp_path)
    assert settings.api_key.get_secret_value() == "environment-secret"
    assert "environment-secret" not in repr(settings)
    assert "api_key" not in settings.model_dump()
    monkeypatch.delenv("NEBIUS_API_KEY")
    assert load_settings(tmp_path).api_key.get_secret_value() == "dotenv-secret"


def test_rtf_credential_loading_and_missing_configuration(tmp_path, monkeypatch):
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    with pytest.raises(ConfigurationError):
        load_settings(tmp_path)
    (tmp_path / "nebius-api-key.rtf").write_text(r"{\rtf1\ansi test-token-value}")
    assert load_settings(tmp_path).api_key.get_secret_value() == "test-token-value"


def test_three_real_samples_have_intact_attributed_source():
    assert len(sample_catalog()) == 3
    for sample in sample_catalog():
        request = load_sample(sample["id"])
        assert request.files
        assert "github.com" in request.origin
