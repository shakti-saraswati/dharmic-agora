from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import httpx


@dataclass
class OpenAICompatibleProvider:
    """
    Minimal OpenAI-compatible chat completions client.

    Many providers expose an OpenAI-compatible `/v1/chat/completions` API.
    This is intentionally small to avoid vendor lock-in.
    """

    base_url: str
    api_key: str
    timeout_s: float = 60.0

    def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 1024,
        extra_headers: Optional[dict[str, str]] = None,
        **_: Any,
    ) -> str:
        url = self.base_url.rstrip("/") + "/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if extra_headers:
            headers.update(extra_headers)
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        with httpx.Client(timeout=self.timeout_s) as client:
            r = client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
            choices = data.get("choices") or []
            if not choices:
                return ""
            msg = choices[0].get("message") or {}
            return str(msg.get("content", ""))

    def generate(
        self,
        *,
        model: str,
        prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> str:
        return self.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

