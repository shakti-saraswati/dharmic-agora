#!/usr/bin/env python3
"""
Token registry for capability elevation.

Supports issue, verify, revoke, and rotate with signed tokens.
"""

from __future__ import annotations

import argparse
import hmac
import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

POLICY_PATH = Path(__file__).parent / "policy" / "token_policy.yaml"
REGISTRY_DIR = Path(__file__).parent.parent / "logs" / "tokens"
REGISTRY_PATH = REGISTRY_DIR / "registry.json"


@dataclass
class TokenRecord:
    token_id: str
    agent_id: str
    capabilities: List[str]
    issued_at: float
    expires_at: float
    nonce: str
    signature: str = ""
    revoked: bool = False
    revoked_at: Optional[str] = None
    revoked_reason: Optional[str] = None
    rotated_from: Optional[str] = None


class TokenRegistry:
    def __init__(self) -> None:
        self.policy = self._load_policy()
        REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
        self.state = self._load_state()

    def _load_policy(self) -> dict:
        if POLICY_PATH.exists():
            return yaml.safe_load(POLICY_PATH.read_text()) or {}
        return {}

    def _load_state(self) -> dict:
        if REGISTRY_PATH.exists():
            return json.loads(REGISTRY_PATH.read_text())
        return {"tokens": []}

    def _save_state(self) -> None:
        REGISTRY_PATH.write_text(json.dumps(self.state, indent=2))

    def _signing_key(self) -> Optional[bytes]:
        signing = self.policy.get("signing", {})
        key_env = signing.get("key_env", "TOKEN_SIGNING_KEY")
        key = os.getenv(key_env)
        return key.encode("utf-8") if key else None

    def _canonical_payload(self, token: TokenRecord) -> bytes:
        data = asdict(token)
        data.pop("signature", None)
        return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def _sign(self, token: TokenRecord) -> str:
        key = self._signing_key()
        if not key:
            return ""
        return hmac.new(key, self._canonical_payload(token), hashlib.sha256).hexdigest()

    def _require_signing(self) -> bool:
        return bool(self.policy.get("signing", {}).get("required", False))

    def issue_token(
        self,
        agent_id: str,
        capabilities: List[str],
        ttl_seconds: Optional[int] = None,
        rotated_from: Optional[str] = None,
    ) -> TokenRecord:
        ttl = ttl_seconds or int(self.policy.get("ttl_seconds", 3600))
        now = time.time()
        token = TokenRecord(
            token_id=str(uuid.uuid4()),
            agent_id=agent_id,
            capabilities=capabilities,
            issued_at=now,
            expires_at=now + ttl,
            nonce=str(uuid.uuid4()),
            rotated_from=rotated_from,
        )
        token.signature = self._sign(token)
        self.state["tokens"].append(asdict(token))
        self._save_state()
        return token

    def revoke_token(self, token_id: str, reason: str) -> TokenRecord:
        if not reason and self.policy.get("revocation", {}).get("require_reason", True):
            raise ValueError("Revocation reason required")
        for item in self.state["tokens"]:
            if item["token_id"] == token_id:
                item["revoked"] = True
                item["revoked_at"] = datetime.now(timezone.utc).isoformat()
                item["revoked_reason"] = reason
                self._save_state()
                return TokenRecord(**item)
        raise ValueError("Token not found")

    def rotate_token(self, token_id: str, ttl_seconds: Optional[int] = None) -> TokenRecord:
        old = self.get_token(token_id)
        self.revoke_token(token_id, reason="rotation")
        return self.issue_token(
            agent_id=old.agent_id,
            capabilities=old.capabilities,
            ttl_seconds=ttl_seconds,
            rotated_from=token_id,
        )

    def get_token(self, token_id: str) -> TokenRecord:
        for item in self.state["tokens"]:
            if item["token_id"] == token_id:
                return TokenRecord(**item)
        raise ValueError("Token not found")

    def list_tokens(self, active_only: bool = False) -> List[TokenRecord]:
        tokens = [TokenRecord(**item) for item in self.state["tokens"]]
        if not active_only:
            return tokens
        now = time.time()
        return [t for t in tokens if not t.revoked and t.expires_at > now]

    def verify_token(self, token_id: str) -> Dict[str, Any]:
        token = self.get_token(token_id)
        now = time.time()
        if token.revoked:
            return {"valid": False, "reason": "revoked"}
        if token.expires_at < now:
            return {"valid": False, "reason": "expired"}
        if self._require_signing():
            key = self._signing_key()
            if not key:
                return {"valid": False, "reason": "signing key missing"}
            expected = self._sign(token)
            if not hmac.compare_digest(token.signature or "", expected):
                return {"valid": False, "reason": "signature invalid"}
        return {"valid": True}


def main() -> None:
    parser = argparse.ArgumentParser(description="Token registry")
    sub = parser.add_subparsers(dest="cmd", required=True)

    issue_p = sub.add_parser("issue", help="Issue a token")
    issue_p.add_argument("--agent", required=True)
    issue_p.add_argument("--cap", action="append", required=True)
    issue_p.add_argument("--ttl", type=int)

    revoke_p = sub.add_parser("revoke", help="Revoke a token")
    revoke_p.add_argument("--token-id", required=True)
    revoke_p.add_argument("--reason", required=True)

    rotate_p = sub.add_parser("rotate", help="Rotate a token")
    rotate_p.add_argument("--token-id", required=True)
    rotate_p.add_argument("--ttl", type=int)

    verify_p = sub.add_parser("verify", help="Verify a token")
    verify_p.add_argument("--token-id", required=True)

    list_p = sub.add_parser("list", help="List tokens")
    list_p.add_argument("--active", action="store_true")

    args = parser.parse_args()
    registry = TokenRegistry()

    if args.cmd == "issue":
        token = registry.issue_token(args.agent, args.cap, args.ttl)
        print(json.dumps(asdict(token), indent=2))
        return
    if args.cmd == "revoke":
        token = registry.revoke_token(args.token_id, args.reason)
        print(json.dumps(asdict(token), indent=2))
        return
    if args.cmd == "rotate":
        token = registry.rotate_token(args.token_id, args.ttl)
        print(json.dumps(asdict(token), indent=2))
        return
    if args.cmd == "verify":
        print(json.dumps(registry.verify_token(args.token_id), indent=2))
        return
    if args.cmd == "list":
        tokens = registry.list_tokens(active_only=args.active)
        print(json.dumps([asdict(t) for t in tokens], indent=2))
        return


if __name__ == "__main__":
    main()
