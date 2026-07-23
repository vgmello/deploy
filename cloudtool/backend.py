"""Terraform azurerm backend configuration from platform config."""

from pathlib import Path

import yaml


class BackendError(Exception):
    pass


def render(platform_path, name, env):
    """-backend-config key=value lines for one tool + environment."""
    platform = yaml.safe_load(Path(platform_path).read_text()) or {}
    state = platform.get("terraform_state") or {}
    for key in ("resource_group", "storage_account", "container"):
        if not state.get(key):
            raise BackendError(f"terraform_state.{key} missing in {platform_path}")
    return [
        f"resource_group_name={state['resource_group']}",
        f"storage_account_name={state['storage_account']}",
        f"container_name={state['container']}",
        f"key={name}/{env}.tfstate",
        "use_oidc=true",
        "use_azuread_auth=true",
    ]
