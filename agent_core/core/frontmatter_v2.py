#!/usr/bin/env python3
"""YAML frontmatter parsing/validation (AIKAGRYA v2).

Goal: enforce a minimal, auditable schema for Markdown artifacts without
requiring PyYAML. This is intentionally a small YAML subset:
  - scalars: `key: value`
  - lists:
      key:
        - item
        - item

If you need full YAML, add a dependency and replace this parser with PyYAML.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Tuple


REQUIRED_FIELDS_V2: List[str] = [
    "title",
    "date",
    "timestamp",
    "location",
    "agent",
    "system_model",
    "agent_id",
    "jikoku",
    "connecting_files",
    "agent_tags",
    "factory_stage",
    "yosemite_grade",
    "readiness_measure",
    "required_reading",
    "pinned",
]

VALID_FACTORY_STAGES = {"Ideation", "Development", "Staging", "Anti-Slop", "Shipping"}

# Accepts: 4.6, 5.0a, 5.10b, 5.15d
_YDS_RE = re.compile(r"^(?P<num>[0-9]\.[0-9]{1,2})(?P<suffix>[abcd])?$")


@dataclass(frozen=True)
class FrontmatterParseResult:
    frontmatter: Dict[str, Any]
    body: str
    errors: List[str]


def _coerce_scalar(value: str) -> Any:
    v = value.strip()
    if v.lower() == "true":
        return True
    if v.lower() == "false":
        return False
    if re.fullmatch(r"-?\d+", v):
        try:
            return int(v)
        except ValueError:
            return v
    if re.fullmatch(r"-?\d+\.\d+", v):
        try:
            return float(v)
        except ValueError:
            return v
    return v


def parse_frontmatter(markdown: str) -> FrontmatterParseResult:
    """Parse frontmatter from markdown and return (frontmatter, body, errors)."""
    lines = markdown.splitlines(True)  # keepends
    if not lines or lines[0].strip() != "---":
        return FrontmatterParseResult({}, markdown, ["Missing opening frontmatter delimiter '---'"])

    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break

    if end_idx is None:
        return FrontmatterParseResult({}, markdown, ["Missing closing frontmatter delimiter '---'"])

    fm_text = "".join(lines[1:end_idx])
    body = "".join(lines[end_idx + 1 :])
    fm, errors = _parse_simple_yaml(fm_text)
    return FrontmatterParseResult(fm, body, errors)


def _parse_simple_yaml(yaml_text: str) -> Tuple[Dict[str, Any], List[str]]:
    errors: List[str] = []
    fm: Dict[str, Any] = {}

    current_key: str | None = None
    current_list: List[Any] | None = None

    for raw_line in yaml_text.splitlines():
        line = raw_line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue

        stripped = line.strip()

        # List item (supports indented `- item`)
        if stripped.startswith("- "):
            if current_key is None:
                errors.append("List item found without a preceding key")
                continue
            if current_list is None:
                current_list = []
                fm[current_key] = current_list
            item = stripped[2:].strip().strip('"').strip("'")
            current_list.append(_coerce_scalar(item))
            continue

        # New key
        if ":" not in line:
            errors.append(f"Invalid frontmatter line (expected key: value): {line}")
            continue

        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()

        # Reset list context when a new key is encountered
        current_key = key
        current_list = None

        if value == "":
            # Potential list key, value will be provided by subsequent `- ` lines.
            fm[key] = []
            current_list = fm[key]
            continue

        unquoted = value.strip('"').strip("'")
        fm[key] = _coerce_scalar(unquoted)

    return fm, errors


def render_frontmatter(frontmatter: Dict[str, Any]) -> str:
    """Render frontmatter dict into a YAML frontmatter block."""
    def _render_value(v: Any) -> List[str]:
        if isinstance(v, bool):
            return ["true" if v else "false"]
        if isinstance(v, (int, float)):
            return [str(v)]
        if isinstance(v, list):
            out: List[str] = [""]
            for item in v:
                out.append(f"  - {item}")
            return out
        return [str(v)]

    lines: List[str] = ["---"]
    for key, value in frontmatter.items():
        rendered = _render_value(value)
        if len(rendered) == 1:
            lines.append(f"{key}: {rendered[0]}")
        else:
            lines.append(f"{key}:{rendered[0]}")
            lines.extend(rendered[1:])
    lines.append("---")
    return "\n".join(lines) + "\n"


def validate_frontmatter_v2(frontmatter: Dict[str, Any]) -> List[str]:
    """Validate frontmatter per AIKAGRYA v2 schema. Returns list of errors."""
    errors: List[str] = []

    for f in REQUIRED_FIELDS_V2:
        if f not in frontmatter:
            errors.append(f"Missing required field: {f}")

    if errors:
        return errors

    # date: YYYY-MM-DD (semantic)
    date = str(frontmatter["date"])
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        errors.append(f"Invalid date (expected YYYY-MM-DD): {date}")

    # timestamp: HH:MM:SS [TZ]
    ts = str(frontmatter["timestamp"])
    if not re.fullmatch(r"\d{2}:\d{2}:\d{2}(?:\s+[A-Za-z0-9:+-]{2,})?", ts):
        errors.append(f"Invalid timestamp (expected HH:MM:SS [TZ]): {ts}")

    # agent_tags: list[str] with @ prefix, prefer exactly 2
    tags = frontmatter.get("agent_tags")
    if not isinstance(tags, list) or not tags:
        errors.append("agent_tags must be a non-empty list")
    else:
        bad = [t for t in tags if not str(t).startswith("@")]
        if bad:
            errors.append(f"agent_tags must start with '@': {bad}")

    # connecting_files: list[str]
    cf = frontmatter.get("connecting_files")
    if not isinstance(cf, list) or not cf:
        errors.append("connecting_files must be a non-empty list")

    # factory_stage: known enum
    stage = str(frontmatter.get("factory_stage"))
    if stage not in VALID_FACTORY_STAGES:
        errors.append(f"factory_stage must be one of {sorted(VALID_FACTORY_STAGES)} (got {stage})")

    # yosemite_grade: YDS-ish
    yds = str(frontmatter.get("yosemite_grade"))
    m = _YDS_RE.match(yds)
    if not m:
        errors.append(f"Invalid yosemite_grade: {yds}")
    else:
        try:
            num = float(m.group("num"))
            if not (0.0 <= num <= 5.15):
                errors.append(f"yosemite_grade numeric part out of range [0.0, 5.15]: {yds}")
        except ValueError:
            errors.append(f"Invalid yosemite_grade numeric part: {yds}")

    # readiness_measure: accept int 0-100 OR string starting with 0-100
    rm = frontmatter.get("readiness_measure")
    readiness_int: int | None = None
    if isinstance(rm, (int, float)):
        readiness_int = int(rm)
    else:
        m2 = re.match(r"^\s*(\d{1,3})", str(rm))
        if m2:
            readiness_int = int(m2.group(1))
    if readiness_int is None or not (0 <= readiness_int <= 100):
        errors.append(f"Invalid readiness_measure (expected 0-100): {rm}")

    # pinned / required_reading: bool
    if not isinstance(frontmatter.get("pinned"), bool):
        errors.append("pinned must be a boolean")
    if not isinstance(frontmatter.get("required_reading"), bool):
        errors.append("required_reading must be a boolean")

    return errors

