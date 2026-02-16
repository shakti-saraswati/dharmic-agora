from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from connectors.sabp_cli import _read_json, _read_json_events


def test_read_json_inline_and_path(tmp_path: Path) -> None:
    inline = _read_json('{"a": 1, "b": "x"}')
    assert inline == {"a": 1, "b": "x"}

    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps({"event_id": "evt-1"}))
    from_path = _read_json(str(payload_path))
    assert from_path == {"event_id": "evt-1"}


def test_read_json_events_array_and_jsonl(tmp_path: Path) -> None:
    events = _read_json_events('[{"event_id":"a"},{"event_id":"b"}]')
    assert [e["event_id"] for e in events] == ["a", "b"]

    jsonl_path = tmp_path / "payloads.jsonl"
    jsonl_path.write_text('{"event_id":"x"}\n{"event_id":"y"}\n')
    from_file = _read_json_events(str(jsonl_path))
    assert [e["event_id"] for e in from_file] == ["x", "y"]


def test_read_json_events_rejects_non_objects() -> None:
    with pytest.raises(ValueError):
        _read_json_events("[1,2,3]")
