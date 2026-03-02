from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from agora import rv_signal


def test_classify_mode_requires_rank_ratio_for_low_rv() -> None:
    mode, warnings = rv_signal.classify_mode(0.62, None)
    assert mode == "uncertain"
    assert "rank_ratio_missing" in warnings


def test_classify_mode_self_ref_when_rv_and_rank_ratio_align() -> None:
    mode, warnings = rv_signal.classify_mode(0.62, 0.7)
    assert mode == "self_ref_structural"
    assert warnings == []


def test_classify_mode_uncertain_when_rv_rank_diverge() -> None:
    mode, warnings = rv_signal.classify_mode(0.62, 0.95)
    assert mode == "uncertain"
    assert "rv_rank_divergence" in warnings


def test_normalize_rv_payload_applies_contract_and_caveats() -> None:
    payload = rv_signal.normalize_rv_payload(
        {
            "rv": 0.61,
            "pr_early": 1.4,
            "pr_late": 0.9,
            "spectral_effective_rank_early": 2.0,
            "spectral_effective_rank_late": 1.2,
            "model_family": "opt",
            "model_name": "opt-6.7b",
            "warnings": ["upstream_warning"],
        }
    )
    assert payload["mode"] == "self_ref_structural"
    assert payload["rank_ratio"] == pytest.approx(0.6)
    assert payload["classification_policy"] == "rv_v1_rank_ratio_companion"
    assert payload["signal_label"] == "experimental"
    assert payload["claim_scope"] == "icl_adaptation_only"
    assert "upstream_warning" in payload["warnings"]
    assert "provisional_thresholds_non_mistral" in payload["warnings"]


def test_normalize_rv_payload_warns_when_pr_components_missing() -> None:
    payload = rv_signal.normalize_rv_payload(
        {
            "rv": 0.7,
            "spectral_effective_rank_early": 2.0,
            "spectral_effective_rank_late": 1.0,
        }
    )
    assert "pr_components_missing" in payload["warnings"]


def test_measure_rv_signal_disabled_without_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SAB_RV_ENDPOINT", raising=False)
    payload = rv_signal.measure_rv_signal("test")
    assert payload["mode"] == "uncertain"
    assert "measurement_disabled" in payload["warnings"]
    assert "no_rv_endpoint" in payload["warnings"]


def test_measure_rv_signal_handles_http_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SAB_RV_ENDPOINT", "http://rv-sidecar/measure")

    class _Response:
        status_code = 503

        @staticmethod
        def json() -> Dict[str, Any]:
            return {}

    monkeypatch.setattr(rv_signal.httpx, "post", lambda *args, **kwargs: _Response())
    payload = rv_signal.measure_rv_signal("test")
    assert "measurement_failed_status" in payload["warnings"]
    assert "http_503" in payload["warnings"]
    assert payload["rv"] is None


def test_measure_rv_signal_unwraps_nested_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SAB_RV_ENDPOINT", "http://rv-sidecar/measure")

    class _Response:
        status_code = 200

        @staticmethod
        def json() -> Dict[str, Any]:
            return {
                "result": {
                    "rv": 0.63,
                    "pr_early": 1.2,
                    "pr_late": 0.8,
                    "spectral_effective_rank_early": 2.0,
                    "spectral_effective_rank_late": 1.0,
                    "model_family": "mistral",
                    "model_name": "mistral-7b-v0.1",
                }
            }

    monkeypatch.setattr(rv_signal.httpx, "post", lambda *args, **kwargs: _Response())
    payload = rv_signal.measure_rv_signal("test")
    assert payload["rv"] == pytest.approx(0.63)
    assert payload["mode"] == "self_ref_structural"
    assert payload["warnings"] == []
