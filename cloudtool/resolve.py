"""Merge a per-environment tool config with platform config into tfvars."""

from pathlib import Path

import yaml


class ResolveError(Exception):
    pass


def resolve(tool, platform_path, env_name):
    platform_path = Path(platform_path)
    if not platform_path.is_file():
        raise ResolveError(
            f"platform config not found: {platform_path} "
            f"(environment '{env_name}' has no platform config file)"
        )
    platform = yaml.safe_load(platform_path.read_text())
    return {"config": {**tool, "environment": env_name, "platform": platform}}
