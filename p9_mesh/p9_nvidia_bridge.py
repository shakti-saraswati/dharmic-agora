#!/usr/bin/env python3
"""
Compatibility wrapper.

This repo renamed "nvidia_core" -> "agent_core" and the bridge accordingly:
  - new: `p9_mesh/p9_agent_core_bridge.py`
  - old: `p9_mesh/p9_nvidia_bridge.py` (this file)

Keep this wrapper so old docs/scripts still work.
"""

from __future__ import annotations

import runpy
from pathlib import Path

def main() -> None:
    # Keep this working when executed as a script (p9_mesh is not a package).
    target = Path(__file__).with_name("p9_agent_core_bridge.py")
    runpy.run_path(str(target), run_name="__main__")


if __name__ == "__main__":
    main()
