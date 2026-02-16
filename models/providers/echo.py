from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class EchoProvider:
    """A deterministic provider for tests and local wiring."""

    name: str = "echo"

    def generate(
        self,
        *,
        model: str,
        prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 256,
        **_: Any,
    ) -> str:
        _ = (temperature, max_tokens)
        return f"[{self.name}:{model}] {prompt}"

