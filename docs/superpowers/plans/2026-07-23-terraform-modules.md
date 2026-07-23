# Terraform Modules (Plan 2 of 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the Terraform layer: a root module consuming `tfvars.json` (`{config: {..., environment, platform}}`), compute modules (`container-app`, `function`, `static-site`) instantiated per manifest entry, shared modules (`keyvault`, `database`, `storage`, `private-endpoint`), naming with single-entry dedupe, and offline tests via `terraform test` with mock providers.

**Architecture:** Root module reads `var.config`, computes all resource names in locals (dedupe rule lives in one place), and composes modules — compute modules receive final names and resolved references only. All tests run offline: `terraform validate`, `terraform test` with `mock_provider`, `tflint`. tfvars fixtures are generated from real manifests through the parse-manifest → resolve-config pipeline and committed; CI regenerates and diffs to keep them honest.

**Tech Stack:** Terraform ≥1.9 (local: 1.15.5), azurerm provider ~> 4.0, random ~> 3.6, terraform test (mock providers), tflint v0.53 + azurerm ruleset.

**Spec:** `docs/superpowers/specs/2026-07-23-cloud-tool-manifest-design.md`

## Global Constraints

- tfvars contract (already golden-tested): `{ "config": { name, environment, apps?, functions?, static_sites?, database?, storage?, platform } }`. Apps are normalized: always `containers` map, ingress always object (`external`, `target_port`, `exposed_port?`, `transport`, `allow_insecure`) or absent (worker).
- Naming: entry base = `<name>-<key>`, deduped to `<name>` when its section has exactly one entry; entry `name:` overrides base. Prefixes: `ca-`, `func-`, `swa-`. Shared: `rg-<name>-<env>`, `kv-<name>-<env>` (≤24 chars, no trailing dash), `psql-`/`sql-<name>-<env>`, `st<name><env>` (alphanumeric ≤24). Identities: `id-<full-resource-name>` (e.g. `id-ca-orders-dev`) — type prefix prevents cross-section collisions (spec amendment).
- Container image resolution: `container.image` if set, else `var.image_tags["<app_key>/<container_key>"]` (functions: `var.image_tags["<function_key>"]`). Workflow (Plan 3) supplies tags for every docker-built container; a container with neither fails the plan loudly.
- Reserved KV secret names: `database-url` → env `DATABASE_URL`; `storage-connection` → env `STORAGE_CONNECTION`. Manifest secrets map `STRIPE_KEY` → KV secret `stripe-key` (lowercase, `_`→`-`); sync-secrets (Plan 3) must write that name.
- Private by default: `public_network_access_enabled = false` + private endpoint unless `public_access: true`; KV/storage deploy-time access via `runner_access: public-allowlist` + `var.runner_ip` allowlist.
- CAE is platform infrastructure: `platform.container_apps_environment_id`.
- Everything testable offline: no `data` sources (ACR ID constructed from parts), no computed-attribute dependencies in strings where a constructed value works (DB FQDN built from name).
- All commands run with `terraform -chdir=terraform` from repo root. Tests: `terraform -chdir=terraform test`.

## File Structure

```
terraform/
├── versions.tf              # terraform + providers + empty azurerm backend
├── providers.tf             # azurerm provider from platform config
├── variables.tf             # config (any), image_tags, runner_ip
├── locals.tf                # ALL naming + entry resolution
├── main.tf                  # RG + module composition
├── outputs.tf               # names map, fqdns
├── modules/
│   ├── container-app/{variables,main,outputs}.tf
│   ├── function/{variables,main,outputs}.tf
│   ├── static-site/{variables,main,outputs}.tf
│   └── shared/
│       ├── keyvault/{variables,main,outputs}.tf
│       ├── database/{variables,main,outputs}.tf
│       ├── storage/{variables,main,outputs}.tf
│       └── private-endpoint/{variables,main,outputs}.tf
├── tests/
│   ├── fixtures/tfvars.{minimal.dev,full.prod,multi.dev,partial.dev}.json   # generated
│   ├── minimal.tftest.hcl
│   ├── full.tftest.hcl
│   ├── multi.tftest.hcl
│   └── partial.tftest.hcl
├── schema/cloud-tool.schema.json     # (exists)
scripts/generate-tf-fixtures.sh
.tflint.hcl
.github/workflows/ci.yml              # + terraform job
```

Tasks below carry the complete code; verification after each task: `terraform -chdir=terraform init -backend=false && terraform -chdir=terraform validate && terraform -chdir=terraform test`, commit per task.

### Task 1: Root skeleton, naming locals, fixtures pipeline, naming tests

Root files (no modules yet, RG only), `scripts/generate-tf-fixtures.sh` running parse-manifest+resolve-config over `tests/fixtures/manifests/{minimal,full,multi,partial}.yml` (dev platform fixture; envs dev/prod/dev/dev), `output "names"` exposing every computed name, and 4 tftest files asserting the naming rules (dedupe, multi-entry suffixing, kv truncation, db engine prefix).

### Task 2: private-endpoint + keyvault modules, wired

KV: RBAC, purge protection off, `public_network_access_enabled` from `runner_access`, network ACLs deny + runner_ip, PE + DNS zone group. Test: kv wiring asserts.

### Task 3: database + storage modules, wired

Database: engine switch postgres (Flexible Server, SKU map B_Standard_B1ms/GP_Standard_D2ds_v4/GP_Standard_D4ds_v4, storage_mb, version 16) vs sqlserver (mssql server 12.0 + database S0/S2/S4, max_size_gb); random admin password; constructed FQDN; connection string → KV secret `database-url`; PE per engine zone. Storage: account TLS1.2/LRS, containers, network rules, PE blob, connection string → `storage-connection`. Tests: multi (sqlserver) + full (postgres) asserts.

### Task 4: container-app module, wired

Identity + KV/ACR role assignments, registry block, KV secret refs (manifest secrets + reserved), conditional ingress block, dynamic containers with env/secret-env/image resolution via `image_tags`. Tests: minimal (single-app dedupe, image tag resolution), full (two apps, worker without ingress), multi (ingress object passthrough, prebuilt image).

### Task 5: function + static-site modules, wired

Function: per-entry storage account + EP1 Linux plan, linux_function_app with VNet integration, UAI + KV reference identity, app_settings = env + `@Microsoft.KeyVault(...)` refs, optional docker stack from image ref (registry/repo/tag parsed). Static site: `azurerm_static_web_app` Free tier + app_settings. Tests: partial (func-partial-dev, swa-partial-dev, EP1).

### Task 6: tflint + CI terraform job

`.tflint.hcl` with azurerm ruleset v0.28; CI `terraform` job: setup-terraform 1.9.8, init -backend=false, validate, fixture regeneration + `git diff --exit-code`, `terraform test`, setup-tflint + `tflint --chdir=terraform --recursive`. Verify local full suite + push branch, PR, CI green.

## Execution note

Executed inline (single session) at the user's direction ("everything should be done") — plan authored with complete code held by the executor; per-task verification loops (`validate` + `test`) replace per-task subagent reviews; a final whole-branch review subagent gates the merge.
