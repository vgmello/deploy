# Cloud Tool Manifest Platform — Design

**Date:** 2026-07-23
**Status:** Approved
**Repo:** `vgmello/deploy`

## Overview

A deployment platform that lets teams deploy Azure resources via Terraform without writing Terraform. Teams describe their app in a small `.cloud-tool.yml` manifest at the root of their repo; a reusable GitHub Actions workflow in this repo translates the manifest into Terraform and deploys it. Behind the scenes each app gets a full stack — compute preset, Key Vault, optional database and storage — wired together over private networking by default.

This repo contains everything: the Terraform modules and presets, the reusable workflow, the composite actions, the manifest JSON Schema, and per-environment platform configuration. App repos hold only the manifest and a thin workflow that calls the reusable one.

## Goals

- Teams declare _what_ they need (apps, functions, static sites, database, storage), never _how_ it is provisioned.
- Sensible defaults for everything; every default overridable in the manifest.
- Private networking by default; public access is an explicit opt-in.
- Per-environment overrides in the manifest; environments defined by the manifest itself.
- Dev deploys automatically on push to main; prod is gated by GitHub environment approval.
- Optional Docker image build when the app is containerized.

## Non-goals (v1)

- Multiple manifests per repo / monorepo support (one manifest per repo; the manifest itself can declare multiple apps/functions).
- Azure SQL, Cosmos DB (Postgres only).
- Redis, Service Bus.
- Postgres AAD auth (v1 uses connection strings in Key Vault).
- Private networking for Static Web Apps (no real private-link story; always public, documented).
- Platform-created VNets (a landing zone is assumed to exist).

## Manifest schema (`.cloud-tool.yml`)

Lives at the root of the app repo. Path overridable via workflow input. `name` plus at least one compute section (`apps`, `functions`, or `static_sites`) required. There is no `type` field — sections define what gets created.

```yaml
# minimal — everything defaulted
name: orders-api
apps:
  api: {}
```

```yaml
# fuller example
name: orders-api

apps: # Azure Container Apps; map key = app identifier
  api:
    port: 8080 # default 8080
    ingress: internal # public | internal | none — default internal; none = worker
    cpu: 0.5 # defaults per entry
    memory: 1Gi
    replicas: { min: 1, max: 3 }
    docker:
      file: ./Dockerfile # docker section or root Dockerfile auto-enables build
      context: .
    env: # plain vars, applied to all envs
      LOG_LEVEL: info
    secrets: # names only; values come from GHA env secrets → Key Vault
      - STRIPE_KEY
  worker:
    ingress: none # worker = container app without ingress

functions: # Azure Function Apps; map key = function app identifier
  processor:
    env:
      QUEUE: jobs

static_sites: {} # Azure Static Web Apps (always public in v1)

database: # section present = resource created
  size: small # t-shirt size → SKU map (small | medium | large), default small
  storage_gb: 32
  public_access: false # default false everywhere

storage: # blob storage account
  containers: [uploads]
  public_access: false

environments: # keys define which envs exist; values deep-merge over the above
  dev: {}
  prod:
    apps:
      api:
        replicas: { min: 2, max: 10 }
        env: { LOG_LEVEL: warn }
    database:
      size: medium
```

Rules:

- `name` is required, plus at least one of `apps`, `functions`, `static_sites` (each non-empty when present).
- Compute sections are maps, not lists — env overlays deep-merge per entry key.
- All entries share one resource group, one Key Vault, and (for apps) one Container Apps environment per env.
- Each entry takes an optional `name:` override for its Azure base name (see Naming).
- A resource section absent = resource not created. Exception: Key Vault is always created.
- `environments:` keys define which environments exist. Each key must have a matching platform config file in this repo (`environments/<env>.yml`); missing file is a hard failure.
- Everything is private by default. Opt out with `public_access: true` or `ingress: public`.
- `ingress: none` produces a worker: a container app with no ingress block.
- T-shirt sizing (`small`/`medium`/`large`) abstracts SKUs. A raw SKU override escape hatch may be added later if needed.
- Manifest is validated against a JSON Schema (`terraform/schema/cloud-tool.schema.json`) before any Azure call.

## Architecture

Chosen approach: **single Terraform root module + translation layer** (over per-preset root modules, which duplicate keyvault/db/network wiring ×3, and codegen, which is unreviewable).

Composite actions parse and deep-merge configuration in this order (later wins):

1. Tool config (manifest top level)
2. Environment overlay (manifest `environments.<env>`)
3. Per-entry defaults (each `apps`/`functions`/`static_sites` entry filled from its defaults file; `database`/`storage` section defaults when present)
4. Platform environment config (`environments/<env>.yml` in this repo)

The result is a single `tfvars.json` consumed by one static Terraform root module. The merge logic lives in composite actions (testable shell/yq), and Terraform stays static and reviewable.

## Repo layout

```
vgmello/deploy
├── .github/
│   ├── workflows/
│   │   └── deploy.yml            # reusable workflow (workflow_call)
│   └── actions/
│       ├── parse-manifest/       # yq: validate + merge → tool.json
│       ├── resolve-config/       # merge platform env config → tfvars.json
│       ├── docker-build/         # build + push to ACR, tag = git sha
│       ├── sync-secrets/         # GHA secrets → Key Vault
│       └── terraform-deploy/     # init/plan/apply with remote state
├── environments/
│   ├── dev.yml                   # platform config: subscription, vnet/subnet IDs,
│   ├── staging.yml               #   private DNS zones, ACR, tfstate account,
│   └── prod.yml                  #   region, naming prefix, deploy SP client id
├── terraform/
│   ├── main.tf                   # root: reads tfvars.json, selects preset
│   ├── modules/
│   │   ├── presets/
│   │   │   ├── container-app/
│   │   │   ├── function/
│   │   │   └── static-site/
│   │   └── shared/
│   │       ├── keyvault/
│   │       ├── postgres/
│   │       ├── storage/
│   │       └── private-endpoint/ # PE + DNS zone group wiring
│   └── schema/
│       └── cloud-tool.schema.json
└── docs/
```

App repo needs only:

```yaml
# .github/workflows/deploy.yml (app repo)
jobs:
  deploy:
    uses: vgmello/deploy/.github/workflows/deploy.yml@v1
    secrets: inherit
```

## Reusable workflow

```
app repo push→main ──► deploy.yml (reusable)

jobs:
  setup                 parse manifest, validate vs JSON Schema,
                        outputs: envs[], docker?, tool name
  build  (if docker)    docker-build action → push ACR, tag = git sha
                        one image per docker-enabled entry, built ONCE;
                        images promoted across envs, never rebuilt
  deploy-<env>          one job per env in manifest key order, chained
                        (e.g. dev → staging → prod). Each:
                          environment: <env>     ← GHA approval gate lives here
                          resolve-config   → tfvars.json
                          sync-secrets     → GHA env secrets → Key Vault
                          terraform-deploy → init/plan/apply
                          summary: app URL, resources changed
```

- **Approvals:** app repos define GitHub environments; prod configured with required reviewers gates automatically. Dev is unprotected, so it deploys immediately. GitHub owns approvals, not the platform.
- **Auth:** OIDC federated credentials to Azure — no stored client secrets. Deploy service principal per environment; IDs live in platform env config.
- **PR behavior:** on `pull_request`, plan-only against dev, plan posted as a PR comment.
- **Env ordering:** manifest key order = deploy order, sequential; first failure stops the chain, later envs untouched.
- **Workflow inputs:** `manifest` (path, default `.cloud-tool.yml`), `environment` (single-env deploy for workflow_dispatch), `plan_only`.
- **Secrets:** `secrets: inherit` from the app repo; `sync-secrets` reads GHA environment secrets matching names listed in the manifest.

## Terraform root + networking

**Root module:**

- Input is the single merged `tfvars.json`. Variable `config` typed `any`; locals normalize with `try()` defaults. Schema validation already happened in GHA.
- Per tool+env: one resource group `rg-<name>-<env>` shared by all entries.
- Compute modules instantiated with `for_each` over the `apps` / `functions` / `static_sites` maps (`container-app` / `function` / `static-site` modules).
- Shared modules are composed by the root, not by compute modules: keyvault (always), one Container Apps environment (if any apps), postgres (if `database`), storage (if `storage`). Compute modules receive resolved references only (Key Vault id, secret names).

**Networking** (all IDs from platform env config):

- No VNets created. Everything attaches to the landing-zone spoke: subnet IDs for the Container Apps environment, private endpoints, and Functions VNet integration.
- `private-endpoint` shared module wires PE + private DNS zone group per resource: postgres, blob, Key Vault, and the app itself when `ingress: internal`.
- Postgres: private access; platform config chooses delegated subnet vs PE per landing-zone convention (default PE); `public_network_access = false` unless `public_access: true`.
- Storage / Key Vault: `public_network_access = false` + PE. Deploy-time access from GHA runners controlled by platform config flag `runner_access: private | public-allowlist` — self-hosted runners inside the VNet for fully private; fallback temporarily allowlists the runner IP during apply.
- Container Apps: one managed environment per tool+env shared by all apps (workload profiles, VNet-integrated, internal by default). `ingress: public` = external ingress; `ingress: none` = no ingress block (worker).
- Static Web Apps: always public frontend in v1; documented limitation.

**State:** `azurerm` backend, storage account from platform config, key `<name>/<env>.tfstate`, locking via blob lease.

## Identity, secrets, naming

**Identity:**

- Each compute entry gets a user-assigned managed identity `id-<base>-<env>` (base per Naming below).
- Grants: Key Vault secrets get/list (RBAC), ACR pull, storage blob contributor (if storage). Postgres AAD auth deferred; v1 uses a connection string in Key Vault.
- Deploy-time SP (OIDC): contributor on app resource groups, network-join on landing-zone subnets, Key Vault secrets-officer (for sync-secrets). Defined per env in platform config.

**Secret flow (end-to-end):**

1. Manifest lists `secrets: [STRIPE_KEY]`.
2. Team adds `STRIPE_KEY` to the app repo's GHA environment secrets.
3. `sync-secrets` writes Key Vault secret `STRIPE_KEY` (idempotent; only writes when the value changed).
4. Terraform wires app env var `STRIPE_KEY` → Key Vault reference (Container Apps secret ref / Functions Key Vault reference). The app sees a plain env var.
5. Platform-generated secrets (postgres connection string, storage connection string) are auto-created in Key Vault and auto-wired as `DATABASE_URL` and `STORAGE_CONNECTION` env vars. These names are reserved and documented.

**Naming** (fixed convention; prefix from platform config):

Per-entry base name: `<manifest-name>-<entry-key>`, deduped to `<manifest-name>` when the section has exactly one entry; an explicit `name:` on the entry overrides the base entirely. Azure resources add the type prefix: `ca-<base>-<env>` (container app), `func-<base>-<env>` (function app), `swa-<base>-<env>` (static site), `id-<base>-<env>` (identity).

Shared per tool+env: `rg-<name>-<env>`, `kv-<name>-<env>` (truncated to 24 chars), `psql-<name>-<env>`, `st<name><env>` (alphanumeric only, truncated to 24), `cae-<name>-<env>`. Truncation collision risk is checked in `parse-manifest`, which warns on collision.

## Error handling

- Manifest validation fails fast in `setup` with human-readable schema errors — before any Azure call.
- Manifest env key without a matching platform env file → hard fail with an explicit message.
- Terraform plan/apply failure: job summary shows a trimmed error; state is never left locked (`-lock-timeout`, apply wrapped so the lease releases).
- Secret listed in the manifest but missing from GHA env secrets → `sync-secrets` fails, listing the missing names (values never logged).
- The env chain stops on first failure; later envs are untouched.

## Testing

- **Composite actions:** bats/shell tests for merge logic (`parse-manifest`, `resolve-config`) with golden files: manifest in → `tfvars.json` out.
- **Terraform:** `terraform validate` + `tflint` in CI; example manifests under `terraform/tests/` planned against mock platform config.
- **Integration:** sandbox subscription, nightly or manual — deploys an example container-app manifest end-to-end, then destroys.
- **Schema:** JSON Schema tested against valid and invalid manifest fixtures.

## Versioning

- Teams pin `@v1` (moving major tag, actions-style). Breaking schema or behavior changes → `v2`.
- Deploy repo CI runs its own tests on PR; major tag advances are manual.
