from __future__ import annotations

from pathlib import Path

import pytest

from models.bus import ModelBus


def test_model_bus_echo_provider(tmp_path: Path):
    cfg = tmp_path / "models.yaml"
    cfg.write_text(
        """
providers:
  echo:
    kind: echo

roles:
  prompt_engineer:
    provider: echo
    model: test-model
    temperature: 0.0
    max_tokens: 8
""".strip()
        + "\n",
        encoding="utf-8",
    )

    bus = ModelBus.load(cfg)
    out = bus.generate("prompt_engineer", "hello")
    assert out.startswith("[echo:test-model] ")


def test_model_bus_fallback(tmp_path: Path):
    cfg = tmp_path / "models.yaml"
    cfg.write_text(
        """
providers:
  echo:
    kind: echo

roles:
  coder:
    provider: missing_provider
    model: wont-work
    fallback:
      - provider: echo
        model: ok
""".strip()
        + "\n",
        encoding="utf-8",
    )

    bus = ModelBus.load(cfg)
    out = bus.generate("coder", "x")
    assert out.startswith("[echo:ok] ")

