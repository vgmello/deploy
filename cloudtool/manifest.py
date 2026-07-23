"""Manifest pipeline: validate .cloud-tool.yml, merge env overlays, normalize.

Normalized shape (per environment) is the Terraform contract: every app has an
explicit ``containers`` map and a full ingress object (or none for workers);
single-container shorthand folds into ``containers.main``.
"""

import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

_PKG = Path(__file__).parent
SCHEMA_PATH = _PKG.parent / "terraform" / "schema" / "cloud-tool.schema.json"
DEFAULTS_DIR = _PKG / "defaults"

CONTAINER_DEFAULTS = {"cpu": 0.5, "memory": "1Gi", "env": {}, "secrets": []}
REPLICA_DEFAULTS = {"min": 1, "max": 3}
SHORTHAND_FIELDS = ("cpu", "memory", "docker", "image", "env", "secrets")


class ManifestError(Exception):
    pass


def deep_merge(base, override):
    """yq `*` semantics: maps merge recursively, arrays and scalars replace."""
    if isinstance(base, dict) and isinstance(override, dict):
        merged = dict(base)
        for key, value in override.items():
            merged[key] = deep_merge(base[key], value) if key in base else value
        return merged
    return override


def _load_yaml(path):
    return yaml.safe_load(Path(path).read_text()) or {}


def validate(manifest):
    """Return human-readable schema violations, empty when valid."""
    schema = json.loads(SCHEMA_PATH.read_text())
    errors = sorted(
        Draft202012Validator(schema).iter_errors(manifest),
        key=lambda e: list(e.absolute_path),
    )
    return [
        f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
        for e in errors
    ]


def _normalize_ingress(app):
    base = {
        "external": False,
        "target_port": app.get("port", 8080),
        "transport": "auto",
        "allow_insecure": False,
    }
    ingress = app.get("ingress")
    if ingress == "none":
        return None
    if ingress is None or ingress == "internal":
        return base
    if ingress == "public":
        return {**base, "external": True}
    return {**base, **ingress}


def _normalize_app(app):
    if "containers" in app:
        containers = app["containers"]
    else:
        containers = {"main": {k: app[k] for k in SHORTHAND_FIELDS if k in app}}
    containers = {k: deep_merge(CONTAINER_DEFAULTS, c) for k, c in containers.items()}

    normalized = {}
    if "name" in app:
        normalized["name"] = app["name"]
    ingress = _normalize_ingress(app)
    if ingress is not None:
        normalized["ingress"] = ingress
    normalized["replicas"] = deep_merge(REPLICA_DEFAULTS, app.get("replicas", {}))
    normalized["containers"] = containers
    return normalized


def normalize(merged):
    cfg = dict(merged)
    if "app" in cfg and "apps" in cfg:
        raise ManifestError(
            "manifest mixes singular app with apps (possibly via an environment overlay); use one form"
        )
    if "app" in cfg:
        cfg["apps"] = {"main": cfg.pop("app")}
    if "apps" in cfg:
        cfg["apps"] = {k: _normalize_app(a) for k, a in cfg["apps"].items()}
    for section, defaults_file in (("functions", "function"), ("static_sites", "static_site")):
        if section in cfg:
            defaults = _load_yaml(DEFAULTS_DIR / f"{defaults_file}.yml")
            cfg[section] = {k: deep_merge(defaults, v) for k, v in cfg[section].items()}
    for section in ("database", "storage"):
        if section in cfg:
            cfg[section] = deep_merge(_load_yaml(DEFAULTS_DIR / f"{section}.yml"), cfg[section])
    return cfg


def _uses_docker_build(tool):
    containers = [
        c
        for app in (tool.get("apps") or {}).values()
        for c in app["containers"].values()
    ]
    entries = containers + list((tool.get("functions") or {}).values())
    return any("docker" in e for e in entries)


def parse(manifest_path, app_root="."):
    """Validate and expand a manifest into per-environment normalized configs.

    Returns (name, environments, tools, docker) where tools maps env -> config.
    """
    manifest = yaml.safe_load(Path(manifest_path).read_text())
    errors = validate(manifest)
    if errors:
        raise ManifestError("manifest validation failed:\n" + "\n".join(errors))

    environments = list(manifest.get("environments") or {"dev": {}})
    base = {k: v for k, v in manifest.items() if k != "environments"}
    tools = {}
    for env in environments:
        overlay = (manifest.get("environments") or {}).get(env) or {}
        tools[env] = normalize(deep_merge(base, overlay))

    docker = any(_uses_docker_build(t) for t in tools.values()) or (
        Path(app_root) / "Dockerfile"
    ).exists()
    return manifest["name"], environments, tools, docker
