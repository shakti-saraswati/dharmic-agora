from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import yaml


@dataclass(frozen=True)
class ProviderConfig:
    kind: str
    base_url: Optional[str] = None
    api_key_env: Optional[str] = None
    timeout_s: float = 60.0


@dataclass(frozen=True)
class RoleConfig:
    provider: str
    model: str
    temperature: float = 0.2
    max_tokens: int = 1024
    # Fallback is a list of role-like overrides tried in-order.
    fallback: Optional[list[dict[str, Any]]] = None


@dataclass(frozen=True)
class ModelBusConfig:
    providers: dict[str, ProviderConfig]
    roles: dict[str, RoleConfig]


def load_config(path: Path) -> ModelBusConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("models config must be a mapping")

    prov_raw = raw.get("providers")
    roles_raw = raw.get("roles")
    if not isinstance(prov_raw, dict) or not isinstance(roles_raw, dict):
        raise ValueError("models config must contain `providers` and `roles` mappings")

    providers: dict[str, ProviderConfig] = {}
    for name, p in prov_raw.items():
        if not isinstance(p, dict):
            raise ValueError(f"provider {name!r} must be a mapping")
        providers[name] = ProviderConfig(
            kind=str(p.get("kind", "")).strip(),
            base_url=p.get("base_url"),
            api_key_env=p.get("api_key_env"),
            timeout_s=float(p.get("timeout_s", 60.0)),
        )
        if not providers[name].kind:
            raise ValueError(f"provider {name!r} missing `kind`")

    roles: dict[str, RoleConfig] = {}
    for role, r in roles_raw.items():
        if not isinstance(r, dict):
            raise ValueError(f"role {role!r} must be a mapping")
        roles[role] = RoleConfig(
            provider=str(r.get("provider", "")).strip(),
            model=str(r.get("model", "")).strip(),
            temperature=float(r.get("temperature", 0.2)),
            max_tokens=int(r.get("max_tokens", 1024)),
            fallback=r.get("fallback"),
        )
        if not roles[role].provider or not roles[role].model:
            raise ValueError(f"role {role!r} missing `provider` or `model`")

    return ModelBusConfig(providers=providers, roles=roles)

