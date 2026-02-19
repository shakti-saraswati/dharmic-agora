from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import httpx


@dataclass
class OllamaProvider:
    base_url: str = "http://localhost:11434"
    timeout_s: float = 60.0

    def generate(
        self,
        *,
        model: str,
        prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        **_: Any,
    ) -> str:
        url = self.base_url.rstrip("/") + "/api/generate"
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        with httpx.Client(timeout=self.timeout_s) as client:
            r = client.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
            return str(data.get("response", ""))

    def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 1024,
        **_: Any,
    ) -> str:
        url = self.base_url.rstrip("/") + "/api/chat"
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        with httpx.Client(timeout=self.timeout_s) as client:
            r = client.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
            # Ollama returns: {"message": {"content": "...", ...}, ...}
            msg = data.get("message") or {}
            return str(msg.get("content", ""))

