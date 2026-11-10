from pathlib import Path

from streamlit.testing.v1 import AppTest

from code_review.config import Settings
from code_review.graph import ReviewWorkflow
from conftest import FakeLLM, successful_specialist

APP = Path(__file__).resolve().parents[1] / "streamlit_app.py"


def configured_app(monkeypatch):
    monkeypatch.setattr("code_review.config.load_settings", lambda: Settings(api_key="test-only"))
    return AppTest.from_file(str(APP), default_timeout=20).run()


def test_app_navigation_and_empty_input(monkeypatch):
    app = configured_app(monkeypatch)
    assert not app.exception
    app.radio(key="source_mode").set_value("Paste code").run()
    assert next(b for b in app.button if b.label == "Run code review →").disabled
    app.radio(key="navigation").set_value("How it works").run()
    assert not app.exception
    app.radio(key="navigation").set_value("Sample reports").run()
    assert not app.exception


def test_ui_review_filters_and_human_resume_do_not_repeat_llm_calls(monkeypatch):
    llm = FakeLLM()
    workflow = ReviewWorkflow(llm, specialist=successful_specialist)
    monkeypatch.setattr("code_review.graph.ReviewWorkflow", lambda *_: workflow)
    app = configured_app(monkeypatch)
    next(b for b in app.button if b.label == "Run code review →").click().run()
    assert not app.exception
    assert len(llm.calls) == 1
    assert app.session_state.active_report["decision"] == "pending"
    app.multiselect(key="live_severity").set_value(["high"]).run()
    assert len(llm.calls) == 1
    next(b for b in app.button if b.label == "Accept report").click().run()
    assert not app.exception
    assert app.session_state.active_report["decision"] == "accepted"
    assert len(llm.calls) == 1
