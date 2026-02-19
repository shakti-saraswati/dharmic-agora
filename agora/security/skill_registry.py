#!/usr/bin/env python3
"""
Signed skill registry verifier.

Ensures the skill registry is allowlisted and signed.
"""

from __future__ import annotations

import argparse
import hmac
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

REGISTRY_PATH = Path(__file__).parent / "skill_registry.yaml"
SIGNATURE_PATH = Path(__file__).parent / "skill_registry.sig"
POLICY_PATH = Path(__file__).parent / "policy" / "skill_registry.yaml"
EVIDENCE_PATH = Path(__file__).parent.parent / "skill_registry_check.json"


@dataclass
class RegistryCheck:
    valid: bool
    reason: str
    signature_valid: bool
    allowlist_ok: bool
    skill_count: int


def _load_policy() -> dict:
    if POLICY_PATH.exists():
        return yaml.safe_load(POLICY_PATH.read_text()) or {}
    return {}


def _canonical_payload(data: dict) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _signing_key(policy: dict) -> Optional[bytes]:
    key_env = policy.get("signing", {}).get("key_env", "SKILL_REGISTRY_SIGNING_KEY")
    value = os.getenv(key_env)
    return value.encode("utf-8") if value else None


def _compute_signature(payload: bytes, key: bytes) -> str:
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def sign_registry() -> str:
    policy = _load_policy()
    key = _signing_key(policy)
    if not key:
        raise RuntimeError("Signing key not available")
    registry = yaml.safe_load(REGISTRY_PATH.read_text()) if REGISTRY_PATH.exists() else {}
    signature = _compute_signature(_canonical_payload(registry), key)
    SIGNATURE_PATH.write_text(signature)
    return signature


def verify_registry() -> RegistryCheck:
    policy = _load_policy()
    registry = yaml.safe_load(REGISTRY_PATH.read_text()) if REGISTRY_PATH.exists() else {}
    skills = registry.get("skills", [])
    allowlist = set(policy.get("allowlist", []) or [])
    allowlist_ok = True
    if allowlist:
        for skill in skills:
            skill_id = skill.get("id")
            if skill_id and skill_id not in allowlist:
                allowlist_ok = False
                break

    signature_valid = True
    if policy.get("signing", {}).get("required", False):
        key = _signing_key(policy)
        if not key or not SIGNATURE_PATH.exists():
            signature_valid = False
        else:
            expected = _compute_signature(_canonical_payload(registry), key)
            actual = SIGNATURE_PATH.read_text().strip()
            signature_valid = hmac.compare_digest(expected, actual)

    valid = allowlist_ok and signature_valid
    reason = "ok" if valid else "signature invalid" if not signature_valid else "allowlist violation"
    return RegistryCheck(
        valid=valid,
        reason=reason,
        signature_valid=signature_valid,
        allowlist_ok=allowlist_ok,
        skill_count=len(skills),
    )


def write_evidence(check: RegistryCheck) -> None:
    EVIDENCE_PATH.write_text(json.dumps(check.__dict__, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Skill registry verifier")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("sign", help="Sign the skill registry")
    sub.add_parser("verify", help="Verify skill registry signature and allowlist")

    args = parser.parse_args()

    if args.cmd == "sign":
        signature = sign_registry()
        print(signature)
        return

    if args.cmd == "verify":
        check = verify_registry()
        write_evidence(check)
        print(json.dumps(check.__dict__, indent=2))
        if not check.valid:
            raise SystemExit(1)
        return


if __name__ == "__main__":
    main()
