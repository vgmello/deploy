"""Terraform init/plan/apply for one environment, with the platform conventions:
per-tool state key, plan-only placeholder tags, runner-IP allowlisting, and a
single retry for RBAC propagation."""

import json
import time
from pathlib import Path

import yaml

from . import backend, builds, gha, runner

PLAN_FILE = "tfplan"


class DeployError(Exception):
    pass


def prepare(platform_path, tool, tool_name, env, image_tags_json, plan_only,
            fetch_ip=runner.fetch_runner_ip):
    """Resolve backend config lines, image tags, and runner IP for a deploy."""
    backend_lines = backend.render(platform_path, tool_name, env)
    tags = json.loads(image_tags_json or "{}")
    platform = yaml.safe_load(Path(platform_path).read_text()) or {}
    if plan_only and not tags:
        registry = (platform.get("acr") or {}).get("login_server", "acr.invalid")
        tags = builds.enumerate_builds(tool, tool_name, registry, "plan-placeholder")["tags"]
    runner_ip = None
    if platform.get("runner_access") == "public-allowlist":
        runner_ip = fetch_ip()
    return backend_lines, tags, runner_ip


def deploy(tf_dir, tfvars_file, backend_lines, tags, runner_ip, env, plan_only,
           targets=(), run=runner.run, sleep=time.sleep):
    """init + plan (+ apply with one retry). Returns the summary line."""
    tf = ["terraform", f"-chdir={tf_dir}"]
    run(tf + ["init", "-input=false"] + [f"-backend-config={line}" for line in backend_lines])

    args = [
        "-input=false",
        f"-var-file={Path(tfvars_file).resolve()}",
        "-var", f"image_tags={json.dumps(tags, separators=(',', ':'))}",
    ]
    if runner_ip:
        args += ["-var", f"runner_ip={runner_ip}"]
    for target in targets:
        args.append(f"-target={target}")

    def plan():
        result = run(tf + ["plan"] + args + [f"-out={PLAN_FILE}"], capture=True)
        print("\n".join(result.stdout.splitlines()[-20:]))

    plan()
    show = run(tf + ["show", "-no-color", PLAN_FILE], capture=True)
    body = "\n".join(show.stdout.splitlines()[:200])
    gha.append_summary(
        f"<details><summary>terraform plan ({env})</summary>\n\n```\n{body}\n```\n</details>"
    )

    if plan_only:
        return f"plan only ({env})"

    apply_cmd = tf + ["apply", "-input=false", PLAN_FILE]
    if run(apply_cmd, check=False).returncode != 0:
        gha.warning("apply failed; retrying once in 30s (RBAC propagation)")
        sleep(30)
        plan()
        run(apply_cmd)
    return f"applied {env}"
