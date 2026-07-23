# Deploy Workflow (Plan 3 of 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The GitHub Actions layer: reusable `deploy.yml` (workflow_call) plus `docker-build`, `sync-secrets`, and `terraform-deploy` composite actions, wiring manifest → images → secrets → Terraform per environment with approval gates.

**Architecture:** Every action wraps a pure, bats-testable script (enumerate-builds, collect-secrets, render-backend-config); cloud CLI calls (az/docker/terraform) live only in action steps. The reusable workflow chains up to 4 indexed deploy jobs (GHA cannot create dynamic sequential jobs); each carries `environment:` so GitHub environment protection gates prod. Build runs once from the first env's tool.json; images promoted across envs.

**Tech Stack:** GitHub Actions (workflow_call, composite actions, OIDC azure/login), bash + jq/yq, bats, actionlint.

**Spec:** `docs/superpowers/specs/2026-07-23-cloud-tool-manifest-design.md` + Plan 2 handoff notes in `docs/superpowers/plans/2026-07-23-terraform-modules.md`.

## Global Constraints

- image_tags contract (Plan 2): key `<app_key>/<container_key>` for apps, `<function_key>` for functions; every container/function without `image:` MUST receive a tag (Terraform fails the plan otherwise). Default build for entries with neither `image:` nor `docker:` is `{file: ./Dockerfile, context: .}`; identical (file, context) pairs build once and are tagged per key.
- Image reference: `<acr_login_server>/<tool-name>/<key with / → ->:<git-sha>`.
- Backend config (Plan 2 handoff): `resource_group_name`/`storage_account_name`/`container_name` from `platform.terraform_state`, `key=<tool-name>/<env>.tfstate`, `use_oidc=true`, `use_azuread_auth=true`.
- KV secret names: manifest `STRIPE_KEY` → KV `stripe-key` (lowercase, `_`→`-`). Missing GHA secrets fail with the list of missing names; values never logged.
- First-deploy ordering (Plan 2 handoff): if the vault does not exist yet and the manifest lists secrets → targeted `terraform apply -target=module.keyvault`, sync secrets, then full apply.
- RBAC propagation (Plan 2 handoff): apply retried once after 30s on first failure.
- Env chain: manifest key order, sequential, max 4 environments (validated in setup), first failure stops the chain. `workflow_call` inputs: `manifest` (default `.cloud-tool.yml`), `environment` (single-env filter), `plan_only`, `deploy_ref` (ref of this repo, default `main`).
- Build-once constraints (documented): docker config must not vary per environment; ACR assumed shared across envs (first env's ACR used).
- `runner_access: public-allowlist` → runner IP detected (`api.ipify.org`) and passed as `TF_VAR_runner_ip`.
- Secrets reach sync-secrets via `env: ALL_SECRETS: ${{ toJSON(secrets) }}` (composite actions cannot enumerate secrets otherwise); app repos use `secrets: inherit`.

## File Structure

```
.github/actions/docker-build/{action.yml,enumerate-builds.sh}
.github/actions/sync-secrets/{action.yml,collect-secrets.sh}
.github/actions/terraform-deploy/{action.yml,render-backend-config.sh}
.github/workflows/deploy.yml          # reusable (workflow_call)
tests/enumerate_builds.bats           # goldens per fixture manifest
tests/collect_secrets.bats
tests/render_backend_config.bats
tests/golden/builds.*.json
docs/usage.md                         # app-repo onboarding snippet
```

### Task 1: enumerate-builds script + docker-build action + golden tests

### Task 2: collect-secrets script + sync-secrets action (vault-missing tolerance) + tests

### Task 3: render-backend-config script + terraform-deploy action (init/plan/apply, retry, runner IP, plan-only placeholder tags) + tests

### Task 4: reusable deploy.yml (setup → build → deploy-0..3 chain) + actionlint + usage doc + spec updates

### Task 5: final whole-branch review (subagent) → fixes → merge

## Execution note

Executed inline (single session), same as Plan 2: per-task verification (bats + actionlint) replaces per-task subagent reviews; final whole-branch review subagent gates the merge. End-to-end workflow execution requires an app repo + Azure OIDC — integration is deferred to a sandbox run (spec's testing section); this plan's tests cover all pure logic offline.
