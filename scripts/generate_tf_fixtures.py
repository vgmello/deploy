#!/usr/bin/env python3
"""Regenerate terraform test fixtures through the real manifest pipeline."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from cloudapp import manifest, resolve  # noqa: E402

PLATFORM = ROOT / "tests" / "fixtures" / "environments" / "dev.yml"
OUT = ROOT / "terraform" / "tests" / "fixtures"

CASES = [("minimal", "dev"), ("full", "prod"), ("multi", "dev"), ("partial", "dev")]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, env in CASES:
        _, _, tools, _ = manifest.parse(ROOT / "tests" / "fixtures" / "manifests" / f"{name}.yml")
        tfvars = resolve.resolve(tools[env], PLATFORM, env)
        path = OUT / f"tfvars.{name}.{env}.json"
        path.write_text(json.dumps(tfvars, indent=2) + "\n")
        print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
