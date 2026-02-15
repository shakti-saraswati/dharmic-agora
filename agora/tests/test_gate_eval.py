"""Tests for SAB Gate Evaluation Harness."""
import json
import pytest
from pathlib import Path
from agora.gate_eval import load_fixtures, evaluate, FIXTURES_PATH


class TestLoadFixtures:
    def test_load_default_fixtures(self):
        fixtures = load_fixtures()
        assert len(fixtures) == 30
        for f in fixtures:
            assert "content" in f
            assert "expected_label" in f
            assert f["expected_label"] in ("genuine", "performative")

    def test_load_custom_fixtures(self, tmp_path):
        p = tmp_path / "test.jsonl"
        entries = [
            {"content": "test content", "expected_label": "genuine", "agent_telos": "testing"},
            {"content": "blah blah", "expected_label": "performative", "agent_telos": ""},
        ]
        with open(p, "w") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")
        fixtures = load_fixtures(p)
        assert len(fixtures) == 2

    def test_genuine_count(self):
        fixtures = load_fixtures()
        genuine = [f for f in fixtures if f["expected_label"] == "genuine"]
        performative = [f for f in fixtures if f["expected_label"] == "performative"]
        assert len(genuine) == 15
        assert len(performative) == 15


class TestEvaluate:
    def test_evaluation_runs(self):
        fixtures = load_fixtures()
        report = evaluate(fixtures)
        assert "gate_metrics" in report
        assert "avg_genuine_composite" in report
        assert "avg_performative_composite" in report
        assert "genuine_beats_performative" in report
        assert report["total_fixtures"] == 30

    def test_genuine_beats_performative(self):
        """The core validation: genuine content should score higher."""
        fixtures = load_fixtures()
        report = evaluate(fixtures)
        assert report["genuine_beats_performative"] is True
        assert report["avg_genuine_composite"] > report["avg_performative_composite"]

    def test_gate_metrics_structure(self):
        fixtures = load_fixtures()
        report = evaluate(fixtures)
        for dim, metrics in report["gate_metrics"].items():
            assert "tp" in metrics
            assert "fp" in metrics
            assert "tn" in metrics
            assert "fn" in metrics
            assert "precision" in metrics
            assert "recall" in metrics
            assert metrics["tp"] + metrics["fp"] + metrics["tn"] + metrics["fn"] == 30

    def test_results_per_fixture(self):
        fixtures = load_fixtures()
        report = evaluate(fixtures)
        assert len(report["results"]) == 30
        for r in report["results"]:
            assert "expected" in r
            assert "admitted" in r
            assert "dimensions" in r
            assert "composite" in r
