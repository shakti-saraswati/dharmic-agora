#!/usr/bin/env python3
"""
Sandbox execution harness.

Default-deny unless docker is available and image is allowlisted.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

import yaml

POLICY_PATH = Path(__file__).parent / "policy" / "sandbox.yaml"


@dataclass
class SandboxResult:
    allowed: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 1
    reason: str = ""


def _load_policy() -> dict:
    if POLICY_PATH.exists():
        return yaml.safe_load(POLICY_PATH.read_text()) or {}
    return {}


def _docker_available() -> bool:
    return shutil.which("docker") is not None


def run_in_sandbox(code: str, image: str) -> SandboxResult:
    policy = _load_policy()
    allowed_images = policy.get("allowed_images", [])
    if image not in allowed_images:
        return SandboxResult(allowed=False, reason="image not allowlisted")
    if not _docker_available():
        return SandboxResult(allowed=False, reason="docker not available")

    limits = policy.get("limits", {})
    cpu = limits.get("cpu", "1")
    memory = limits.get("memory", "512m")
    timeout = limits.get("timeout_seconds", 30)
    network = policy.get("network", False)

    with tempfile.TemporaryDirectory() as tmp:
        script_path = Path(tmp) / "sandbox.py"
        script_path.write_text(code)

        cmd = [
            "docker", "run", "--rm",
            "--cpus", str(cpu),
            "--memory", str(memory),
        ]
        if not network:
            cmd += ["--network", "none"]
        cmd += ["-v", f"{tmp}:/work", "-w", "/work", image, "python", "sandbox.py"]

        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return SandboxResult(
                allowed=True,
                stdout=proc.stdout,
                stderr=proc.stderr,
                exit_code=proc.returncode,
                reason="ok" if proc.returncode == 0 else "nonzero exit",
            )
        except subprocess.TimeoutExpired:
            return SandboxResult(allowed=True, reason="timeout", exit_code=124)
        except Exception as e:
            return SandboxResult(allowed=False, reason=f"sandbox error: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Sandbox harness")
    parser.add_argument("--code", help="Path to code file")
    parser.add_argument("--image", default="python:3.11-slim")
    args = parser.parse_args()

    if not args.code:
        print("--code is required")
        raise SystemExit(1)

    code = Path(args.code).read_text()
    result = run_in_sandbox(code, args.image)
    print(json.dumps(asdict(result), indent=2))
    if not result.allowed or result.exit_code != 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
