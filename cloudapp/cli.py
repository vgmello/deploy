"""Command-line entrypoints used by the composite actions."""

import argparse
import json
import os
import sys
from pathlib import Path

from . import backend, builds, dockerbuild, gha, manifest, resolve, runner, secrets, tfdeploy


def _load_json(path):
    return json.loads(Path(path).read_text())


def _write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2) + "\n")


def cmd_parse_manifest(args):
    name, environments, tools, docker = manifest.parse(args.manifest, args.app_root)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    for stale in list(out.glob("tool.*.json")) + [out / "outputs.txt"]:
        if stale.exists():
            stale.unlink()
    for env, tool in tools.items():
        _write_json(out / f"tool.{env}.json", tool)
    gha.write_outputs(
        {
            "name": name,
            "environments": json.dumps(environments, separators=(",", ":")),
            "docker": str(docker).lower(),
        },
        fallback_file=out / "outputs.txt",
    )


def cmd_resolve_config(args):
    tool = _load_json(args.tool_json)
    tfvars = resolve.resolve(tool, args.platform_file, args.environment)
    _write_json(args.out_file, tfvars)


def cmd_enumerate_builds(args):
    plan = builds.enumerate_builds(_load_json(args.tool_json), args.tool_name, args.registry, args.git_sha)
    print(json.dumps(plan, indent=2))


def cmd_docker_build(args):
    plan = builds.enumerate_builds(_load_json(args.tool_json), args.tool_name, args.registry, args.git_sha)
    dockerbuild.build_and_push(plan, args.registry, runner.run)
    gha.write_outputs({"image-tags": json.dumps(plan["tags"], separators=(",", ":"))})


def cmd_sync_secrets(args):
    tool = _load_json(args.tool_json)
    all_secrets = json.loads(os.environ.get("ALL_SECRETS") or "{}")
    outputs = secrets.sync(
        tool,
        args.keyvault_name,
        all_secrets,
        runner.run,
        require_vault=args.require_vault,
    )
    gha.write_outputs(outputs)


def cmd_terraform_deploy(args):
    tool = _load_json(args.tool_json)
    backend_lines, tags, runner_ip = tfdeploy.prepare(
        args.platform_file, tool, args.tool_name, args.environment,
        args.image_tags, args.plan_only,
    )
    summary = tfdeploy.deploy(
        args.terraform_dir, args.tfvars_file, backend_lines, tags, runner_ip,
        args.environment, args.plan_only, targets=args.targets.split(),
    )
    gha.write_outputs({"summary": summary})


def main(argv=None):
    parser = argparse.ArgumentParser(prog="cloudapp")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("parse-manifest")
    p.add_argument("--manifest", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--app-root", default=".")
    p.set_defaults(func=cmd_parse_manifest)

    p = sub.add_parser("resolve-config")
    p.add_argument("--tool-json", required=True)
    p.add_argument("--platform-file", required=True)
    p.add_argument("--environment", required=True)
    p.add_argument("--out-file", required=True)
    p.set_defaults(func=cmd_resolve_config)

    p = sub.add_parser("enumerate-builds")
    p.add_argument("--tool-json", required=True)
    p.add_argument("--tool-name", required=True)
    p.add_argument("--registry", required=True)
    p.add_argument("--git-sha", required=True)
    p.set_defaults(func=cmd_enumerate_builds)

    p = sub.add_parser("docker-build")
    p.add_argument("--tool-json", required=True)
    p.add_argument("--tool-name", required=True)
    p.add_argument("--registry", required=True)
    p.add_argument("--git-sha", required=True)
    p.set_defaults(func=cmd_docker_build)

    p = sub.add_parser("sync-secrets")
    p.add_argument("--tool-json", required=True)
    p.add_argument("--keyvault-name", required=True)
    p.add_argument("--require-vault", action="store_true")
    p.set_defaults(func=cmd_sync_secrets)

    p = sub.add_parser("terraform-deploy")
    p.add_argument("--terraform-dir", required=True)
    p.add_argument("--tfvars-file", required=True)
    p.add_argument("--tool-json", required=True)
    p.add_argument("--tool-name", required=True)
    p.add_argument("--environment", required=True)
    p.add_argument("--platform-file", required=True)
    p.add_argument("--image-tags", default="{}")
    p.add_argument("--plan-only", action="store_true")
    p.add_argument("--targets", default="")
    p.set_defaults(func=cmd_terraform_deploy)

    args = parser.parse_args(argv)
    try:
        args.func(args)
    except (manifest.ManifestError, resolve.ResolveError, secrets.SyncError,
            tfdeploy.DeployError, backend.BackendError) as exc:
        gha.error(str(exc))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
