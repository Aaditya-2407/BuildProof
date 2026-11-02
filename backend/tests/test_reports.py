from __future__ import annotations

from app import analyzer
from app.scanner import build_fact_sheet


def test_missing_readme_report_marks_purpose_as_an_evidence_based_inference(monkeypatch):
    fact_sheet = build_fact_sheet(
        {"app.py": "from flask import Flask\napp = Flask(__name__)\n"}, [],
        {"full_name": "demo/no-readme", "commit_sha": "abc123", "url": "https://github.com/demo/no-readme"},
        1,
    )
    evidence_id = fact_sheet["evidence"][0]["id"]
    response = {
        "overview": "This small repository initializes a Flask application.",
        "purpose": {"summary": "A minimal Flask web app (inferred).", "confidence": "medium",
                    "is_inference": True, "evidence_ids": [evidence_id]},
        "architecture_flow": [{"step": "App setup", "detail": "The module creates a Flask application.",
                                "evidence_ids": [evidence_id]}],
        "judge_questions": [{"category": "architecture", "question": f"How does route {index} work?",
                             "why": "The source shows app initialization.", "evidence_ids": [evidence_id],
                             "answer_outline": ["Explain the Flask app setup."], "follow_up": "What would you add?"}
                            for index in range(5)],
        "_model_provider": "gemini",
    }
    monkeypatch.setattr(analyzer, "_request_model", lambda *args, **kwargs: dict(response))

    report = analyzer.build_report(fact_sheet)

    assert report["purpose"]["is_inference"] is True
    assert report["purpose"]["confidence"] == "medium"
    assert report["documentation_and_compliance"]["readme_present"] is False
    assert report["model_provider"] == "gemini"
