from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional

from .config import ModelBusConfig, RoleConfig, load_config
from .providers import EchoProvider, OllamaProvider, OpenAICompatibleProvider


class ModelBus:
    """
    Route model calls by role.

    This is the "load any model / any provider" seam. Swarms should depend on this
    interface instead of hard-coding vendor SDKs.
    """

    def __init__(self, cfg: ModelBusConfig, base_url: str | None = None):
        self.cfg = cfg
        self.base_url = base_url.rstrip("/") if base_url else None
        self._providers: dict[str, Any] = {}

    def health_check(self) -> dict[str, Any]:
        """Lightweight, mock-friendly readiness check."""
        return {
            "status": "ok",
            "providers": sorted(self.cfg.providers.keys()),
            "roles": sorted(self.cfg.roles.keys()),
            "provider_count": len(self.cfg.providers),
            "role_count": len(self.cfg.roles),
            "base_url_override": self.base_url,
        }

    @classmethod
    def load(cls, path: Path, base_url: str | None = None) -> "ModelBus":
        return cls(load_config(path), base_url=base_url)

    def provider(self, name: str) -> Any:
        if name in self._providers:
            return self._providers[name]

        if name not in self.cfg.providers:
            raise KeyError(f"unknown provider: {name}")

        p = self.cfg.providers[name]
        kind = p.kind.lower()

        if kind == "echo":
            inst = EchoProvider(name=name)
        elif kind == "ollama":
            inst = OllamaProvider(
                base_url=self.base_url or p.base_url or "http://localhost:11434",
                timeout_s=p.timeout_s,
            )
        elif kind in {"openai_compatible", "openai-compatible", "openai"}:
            import os

            if not p.api_key_env:
                raise ValueError(f"provider {name} missing api_key_env")
            api_key = os.getenv(p.api_key_env, "")
            if not api_key:
                raise ValueError(f"env var {p.api_key_env} not set for provider {name}")
            inst = OpenAICompatibleProvider(
                base_url=(self.base_url or p.base_url or "https://api.openai.com/v1").rstrip("/"),
                api_key=api_key,
                timeout_s=p.timeout_s,
            )
        else:
            raise ValueError(f"unknown provider kind: {p.kind}")

        self._providers[name] = inst
        return inst

    def _role_plans(self, role: str) -> list[RoleConfig]:
        if role not in self.cfg.roles:
            raise KeyError(f"unknown role: {role}")
        base = self.cfg.roles[role]
        plans: list[RoleConfig] = [base]

        if base.fallback:
            base_dict = asdict(base)
            # Fallback plans shouldn't themselves carry the whole fallback list.
            base_dict.pop("fallback", None)
            for fb in base.fallback:
                if not isinstance(fb, dict):
                    continue
                merged = dict(base_dict)
                merged.update(fb)
                merged["fallback"] = None
                plans.append(RoleConfig(**merged))

        return plans

    def generate(self, role: str, prompt: str) -> str:
        last_err: Optional[Exception] = None

        for plan in self._role_plans(role):
            try:
                prov = self.provider(plan.provider)
                return prov.generate(
                    model=plan.model,
                    prompt=prompt,
                    temperature=plan.temperature,
                    max_tokens=plan.max_tokens,
                )
            except Exception as e:  # pragma: no cover (fallback errors vary)
                last_err = e
                continue

        assert last_err is not None
        raise last_err

    def chat(self, role: str, messages: list[dict[str, str]]) -> str:
        last_err: Optional[Exception] = None
        for plan in self._role_plans(role):
            try:
                prov = self.provider(plan.provider)
                if hasattr(prov, "chat"):
                    return prov.chat(
                        model=plan.model,
                        messages=messages,
                        temperature=plan.temperature,
                        max_tokens=plan.max_tokens,
                    )
                # Fallback: flatten to a prompt.
                prompt = "\n".join(f"{m.get('role','user')}: {m.get('content','')}" for m in messages)
                return prov.generate(
                    model=plan.model,
                    prompt=prompt,
                    temperature=plan.temperature,
                    max_tokens=plan.max_tokens,
                )
            except Exception as e:  # pragma: no cover
                last_err = e
                continue

        assert last_err is not None
        raise last_err
