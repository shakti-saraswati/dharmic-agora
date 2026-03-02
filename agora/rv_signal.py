#!/usr/bin/env python3
"""
R_V experimental signal integration for SAB.

This module intentionally treats R_V as an experimental structural signal
for in-context adaptation (ICL), not a consciousness or persistence claim.
"""

from __future__ import annotations

import math
import os
from typing import Any, Dict, List, Optional, Tuple

import httpx

SELF_REF_THRESHOLD = 0.737
BASELINE_THRESHOLD = 0.85
RANK_RATIO_SELF_REF_MAX = 0.85

VALID_MODES = {"self_ref_structural", "baseline", "uncertain"}
DEFAULT_MEASUREMENT_VERSION = "rv-1.0.0-bfloat16-w16"
DEFAULT_MODEL_FAMILY = "mistral"
DEFAULT_MODEL_NAME = "mistral-7b-v0.1"
CLASSIFICATION_POLICY = "rv_v1_rank_ratio_companion"


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        val = float(value)
        return val if math.isfinite(val) else None
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            val = float(raw)
        except ValueError:
            return None
        return val if math.isfinite(val) else None
    return None


def _to_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return int(value)
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError:
            return None
    return None


def _normalize_warnings(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    out: List[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
    return out


def classify_mode(rv: Optional[float], rank_ratio: Optional[float]) -> Tuple[str, List[str]]:
    warnings: List[str] = []
    if rv is None:
        warnings.append("rv_missing")
        return "uncertain", warnings

    if rv < SELF_REF_THRESHOLD:
        if rank_ratio is None:
            warnings.append("rank_ratio_missing")
            return "uncertain", warnings
        if rank_ratio >= RANK_RATIO_SELF_REF_MAX:
            warnings.append("rv_rank_divergence")
            return "uncertain", warnings
        return "self_ref_structural", warnings

    if rv > BASELINE_THRESHOLD:
        return "baseline", warnings

    return "uncertain", warnings


def _extract_rank_ratio(raw: Dict[str, Any], *, early: Optional[float], late: Optional[float]) -> Optional[float]:
    direct = _to_float(raw.get("rank_ratio"))
    if direct is not None:
        return direct

    if early is None or late is None:
        return None
    if abs(early) < 1e-12:
        return None
    return late / early


def normalize_rv_payload(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raw = {}

    rv = _to_float(raw.get("rv"))
    if rv is None:
        # Backward compatibility from earlier drafts.
        rv = _to_float(raw.get("rv_contraction"))

    pr_early = _to_float(raw.get("pr_early"))
    pr_late = _to_float(raw.get("pr_late"))
    ser_early = _to_float(raw.get("spectral_effective_rank_early"))
    ser_late = _to_float(raw.get("spectral_effective_rank_late"))
    rank_ratio = _extract_rank_ratio(raw, early=ser_early, late=ser_late)

    derived_mode, derived_warnings = classify_mode(rv, rank_ratio)
    warnings = _normalize_warnings(raw.get("warnings"))
    warnings.extend(derived_warnings)
    if rv is not None and (pr_early is None or pr_late is None):
        warnings.append("pr_components_missing")

    # Deduplicate while preserving order.
    seen = set()
    dedup_warnings: List[str] = []
    for item in warnings:
        if item in seen:
            continue
        seen.add(item)
        dedup_warnings.append(item)

    measurement_version = str(
        raw.get("measurement_version")
        or os.getenv("SAB_RV_MEASUREMENT_VERSION", DEFAULT_MEASUREMENT_VERSION)
    )
    model_family = str(raw.get("model_family") or DEFAULT_MODEL_FAMILY)
    model_name = str(raw.get("model_name") or DEFAULT_MODEL_NAME)
    family_norm = model_family.lower()
    name_norm = model_name.lower()
    if "mistral" not in family_norm and "mistral" not in name_norm and "provisional_thresholds_non_mistral" not in dedup_warnings:
        dedup_warnings.append("provisional_thresholds_non_mistral")

    out = {
        "rv": rv,
        "pr_early": pr_early,
        "pr_late": pr_late,
        "mode": derived_mode,
        "cosine_similarity": _to_float(raw.get("cosine_similarity")),
        "spectral_effective_rank_early": ser_early,
        "spectral_effective_rank_late": ser_late,
        "rank_ratio": rank_ratio,
        "spectral_top1_ratio_late": _to_float(raw.get("spectral_top1_ratio_late")),
        "attn_entropy": _to_float(raw.get("attn_entropy")),
        "model_family": model_family,
        "model_name": model_name,
        "early_layer": _to_int(raw.get("early_layer")),
        "late_layer": _to_int(raw.get("late_layer")),
        "window_size": _to_int(raw.get("window_size")),
        "measurement_version": measurement_version,
        "classification_policy": CLASSIFICATION_POLICY,
        "warnings": dedup_warnings,
        # Policy labels from MI guidance:
        "signal_label": os.getenv("SAB_RV_SIGNAL_LABEL", "experimental"),
        "claim_scope": "icl_adaptation_only",
    }
    return out


def _unwrap_measure_response(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    # Support multiple sidecar conventions.
    for key in ("result", "data", "measurement"):
        candidate = payload.get(key)
        if isinstance(candidate, dict):
            return candidate
    return payload


def measure_rv_signal(content: str) -> Dict[str, Any]:
    endpoint = os.getenv("SAB_RV_ENDPOINT", "").strip()
    timeout = float(os.getenv("SAB_RV_TIMEOUT_SECONDS", "3.0"))

    if not endpoint:
        payload = normalize_rv_payload({})
        payload["warnings"].extend(["measurement_disabled", "no_rv_endpoint"])
        return payload

    try:
        response = httpx.post(
            endpoint,
            json={
                "text": content,
                "content": content,
                "prompt": content,
            },
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        payload = normalize_rv_payload({})
        payload["warnings"].extend(["measurement_failed_http", str(exc.__class__.__name__)])
        return payload

    if response.status_code >= 400:
        payload = normalize_rv_payload({})
        payload["warnings"].extend(["measurement_failed_status", f"http_{response.status_code}"])
        return payload

    try:
        raw = response.json()
    except ValueError:
        payload = normalize_rv_payload({})
        payload["warnings"].append("measurement_failed_json_decode")
        return payload

    normalized = normalize_rv_payload(_unwrap_measure_response(raw))
    if normalized["rv"] is None:
        normalized["warnings"].append("rv_null_from_provider")
    return normalized
