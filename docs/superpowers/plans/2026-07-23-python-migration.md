# Python Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (executed inline, same pattern as Plans 2-3).

**Goal:** Replace every shell/jq/yq core in the composite actions with one small Python package (`cloudtool/`) tested by pytest, so all logic — including the previously untested az/docker/terraform glue — is unit-tested, maintainable, and succinct.

**Architecture:** `cloudtool/` at repo root: `manifest` (validate via jsonschema, deep-merge matching yq `*` semantics, normalize replacing normalize.jq), `resolve`, `builds`, `secrets` (collect + sync with injected subprocess runner), `backend`, `dockerbuild`, `tfdeploy` (terraform init/plan/apply with retry), `gha` (outputs/summary/annotations), `runner` (subprocess wrapper — the mock seam), `cli` (argparse). Actions become `pip install -r requirements.txt` + `python3 -m cloudtool <cmd>`. Defaults YAMLs move into `cloudtool/defaults/`. Existing `tests/golden/*` are the parity contract; bats is retired and every bats test is ported to pytest, plus new tests for the glue paths (vault-missing/defer/require, secret idempotency + retry, build dedupe/tag/push sequences, apply retry, plan-only placeholders). Terraform fixtures regenerate via the Python pipeline (content-identical, literal format may differ).

**Wins:** kills the npx ajv download in the deploy path, jq/yq runtime deps, SIGPIPE-class shell hazards; one language, one test framework.

## Global Constraints

- Behavior parity: all golden files pass unchanged (parsed comparison); terraform `tftest` suite stays green on regenerated fixtures; action inputs/outputs contracts unchanged (`name`, `environments` compact JSON, `docker`, `vault-exists`, `secret-count`, `image-tags`, `summary`).
- Deep-merge semantics = yq `*`: maps merged recursively, arrays and scalars replaced.
- Python 3.11+ stdlib + PyYAML + jsonschema (pinned in requirements.txt); pytest in requirements-dev.txt. No other deps.
- All az/docker/terraform/network calls go through injectable seams (`runner.run`, ip fetcher, sleeper) — every branch unit-testable without cloud access.
- CI: bats job replaced by pytest; actionlint and terraform jobs stay; fixture-sync check now runs the Python generator.

## Tasks

1. `cloudtool/` package: gha, runner, manifest (+defaults move), resolve, builds, secrets, backend, dockerbuild, tfdeploy, cli.
2. pytest suite: port all 44 bats tests + new glue tests; parity against existing goldens.
3. Rewrite 5 action.ymls as thin python adapters; delete .sh/.jq/bats; regenerate terraform fixtures via `scripts/generate_tf_fixtures.py`; verify terraform test.
4. CI update, spec Testing section update, push PR, CI green, final review subagent, merge.
