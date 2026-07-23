# Cloud Tool Foundation (Plan 1 of 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the manifest layer of the cloud-tool platform: JSON Schema validation, preset defaults, the `parse-manifest` and `resolve-config` composite actions, example platform environment configs, and CI — all golden-file tested with no Azure dependency.

**Architecture:** Shell scripts (yq/jq) inside composite action directories do all merge logic so they are testable locally with bats. Merge order: preset defaults → manifest top level → manifest env overlay → platform env config. Output of the chain is one `tfvars.json` per environment, consumed later by the Terraform root module (Plan 2).

**Tech Stack:** bash, mikefarah yq v4, jq, ajv-cli (via npx), bats-core, GitHub composite actions, actionlint.

**Spec:** `docs/superpowers/specs/2026-07-23-cloud-tool-manifest-design.md`

## Global Constraints

- Only `name` and `type` are required manifest fields; everything else defaults.
- Private by default: `ingress: internal`, `public_access: false` in all defaults.
- Manifest `environments:` keys define which envs exist; no `environments:` section → envs = `["dev"]`.
- A resource section absent = resource not created; defaults for `database`/`storage` apply only when the section is present.
- yq is mikefarah v4 syntax everywhere (`brew install yq`). jq required. Node required (npx ajv-cli).
- All scripts `set -euo pipefail`, executable (`chmod +x`).
- Run tests with `bats tests/` from repo root. Local prerequisites: `brew install yq jq bats-core`.

## File Structure

```
terraform/schema/cloud-tool.schema.json        # manifest JSON Schema (draft 2020-12)
.github/actions/parse-manifest/
├── action.yml                                 # composite wrapper
├── parse-manifest.sh                          # validate + merge → tool.<env>.json
└── defaults/
    ├── container-app.yml                      # preset defaults
    ├── function.yml
    ├── static-site.yml
    ├── database.yml                           # section defaults
    └── storage.yml
.github/actions/resolve-config/
├── action.yml
└── resolve-config.sh                          # tool.json + platform env → tfvars.json
environments/{dev,staging,prod}.yml            # platform env config examples
tests/
├── schema.bats
├── parse_manifest.bats
├── resolve_config.bats
├── fixtures/manifests/*.yml
└── golden/*.json
.github/workflows/ci.yml
```

---

### Task 1: Manifest JSON Schema

**Files:**

- Create: `terraform/schema/cloud-tool.schema.json`
- Create: `tests/fixtures/manifests/minimal.yml`
- Create: `tests/fixtures/manifests/full.yml`
- Create: `tests/fixtures/manifests/invalid-missing-name.yml`
- Create: `tests/fixtures/manifests/invalid-bad-type.yml`
- Create: `tests/fixtures/manifests/invalid-unknown-key.yml`
- Test: `tests/schema.bats`

**Interfaces:**

- Consumes: nothing.
- Produces: `terraform/schema/cloud-tool.schema.json` (path used by Task 2's script); fixture manifests `minimal.yml` and `full.yml` reused by Tasks 2–5 golden tests.

- [ ] **Step 1: Write fixtures**

`tests/fixtures/manifests/minimal.yml`:

```yaml
name: orders-api
type: container-app
```

`tests/fixtures/manifests/full.yml` (the spec's full example):

```yaml
name: orders-api
type: container-app

app:
  port: 8080
  ingress: internal
  cpu: 0.5
  memory: 1Gi
  replicas: { min: 1, max: 3 }
  docker:
    file: ./Dockerfile
    context: .
  env:
    LOG_LEVEL: info
  secrets:
    - STRIPE_KEY

database:
  size: small
  storage_gb: 32
  public_access: false

storage:
  containers: [uploads]
  public_access: false

environments:
  dev: {}
  prod:
    app:
      replicas: { min: 2, max: 10 }
      env: { LOG_LEVEL: warn }
    database:
      size: medium
```

`tests/fixtures/manifests/invalid-missing-name.yml`:

```yaml
type: container-app
```

`tests/fixtures/manifests/invalid-bad-type.yml`:

```yaml
name: orders-api
type: virtual-machine
```

`tests/fixtures/manifests/invalid-unknown-key.yml`:

```yaml
name: orders-api
type: container-app
databse:
  size: small
```

- [ ] **Step 2: Write the failing test**

`tests/schema.bats`:

```bash
#!/usr/bin/env bats

setup() {
  REPO_ROOT="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"
  SCHEMA="$REPO_ROOT/terraform/schema/cloud-tool.schema.json"
  FIXTURES="$REPO_ROOT/tests/fixtures/manifests"
  TMP="$(mktemp -d)"
}

teardown() { rm -rf "$TMP"; }

validate() {
  yq -o=json '.' "$FIXTURES/$1" > "$TMP/m.json"
  npx --yes ajv-cli@5 validate --spec=draft2020 -s "$SCHEMA" -d "$TMP/m.json"
}

@test "minimal manifest is valid" {
  run validate minimal.yml
  [ "$status" -eq 0 ]
}

@test "full manifest is valid" {
  run validate full.yml
  [ "$status" -eq 0 ]
}

@test "missing name is invalid" {
  run validate invalid-missing-name.yml
  [ "$status" -ne 0 ]
}

@test "bad type is invalid" {
  run validate invalid-bad-type.yml
  [ "$status" -ne 0 ]
}

@test "unknown top-level key is invalid" {
  run validate invalid-unknown-key.yml
  [ "$status" -ne 0 ]
}
```

- [ ] **Step 3: Run test to verify it fails**

Run: `bats tests/schema.bats`
Expected: all 5 tests FAIL (schema file does not exist).

- [ ] **Step 4: Write the schema**

`terraform/schema/cloud-tool.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://github.com/vgmello/deploy/terraform/schema/cloud-tool.schema.json",
  "title": "cloud-tool manifest",
  "type": "object",
  "additionalProperties": false,
  "required": ["name", "type"],
  "properties": {
    "name": { "type": "string", "pattern": "^[a-z][a-z0-9-]{1,29}$" },
    "type": { "enum": ["container-app", "function", "static-site"] },
    "app": { "$ref": "#/$defs/app" },
    "database": { "$ref": "#/$defs/database" },
    "storage": { "$ref": "#/$defs/storage" },
    "environments": {
      "type": "object",
      "propertyNames": { "pattern": "^[a-z][a-z0-9]{1,15}$" },
      "additionalProperties": { "$ref": "#/$defs/overlay" }
    }
  },
  "$defs": {
    "app": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "port": { "type": "integer", "minimum": 1, "maximum": 65535 },
        "ingress": { "enum": ["public", "internal", "none"] },
        "cpu": { "type": "number", "exclusiveMinimum": 0 },
        "memory": { "type": "string", "pattern": "^[0-9]+(\\.[0-9]+)?Gi$" },
        "replicas": {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "min": { "type": "integer", "minimum": 0 },
            "max": { "type": "integer", "minimum": 1 }
          }
        },
        "docker": {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "file": { "type": "string" },
            "context": { "type": "string" }
          }
        },
        "env": {
          "type": "object",
          "additionalProperties": { "type": "string" }
        },
        "secrets": {
          "type": "array",
          "items": { "type": "string", "pattern": "^[A-Z][A-Z0-9_]*$" }
        }
      }
    },
    "database": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "size": { "enum": ["small", "medium", "large"] },
        "storage_gb": { "type": "integer", "minimum": 32, "maximum": 16384 },
        "public_access": { "type": "boolean" }
      }
    },
    "storage": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "containers": {
          "type": "array",
          "items": {
            "type": "string",
            "pattern": "^[a-z0-9](?:[a-z0-9-]{1,61})?[a-z0-9]$"
          }
        },
        "public_access": { "type": "boolean" }
      }
    },
    "overlay": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "app": { "$ref": "#/$defs/app" },
        "database": { "$ref": "#/$defs/database" },
        "storage": { "$ref": "#/$defs/storage" }
      }
    }
  }
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `bats tests/schema.bats`
Expected: 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add terraform/schema tests
git commit -m "feat: add cloud-tool manifest JSON Schema with fixture validation tests"
```

---

### Task 2: parse-manifest merge script

**Files:**

- Create: `.github/actions/parse-manifest/parse-manifest.sh`
- Create: `.github/actions/parse-manifest/defaults/container-app.yml`
- Create: `.github/actions/parse-manifest/defaults/function.yml`
- Create: `.github/actions/parse-manifest/defaults/static-site.yml`
- Create: `.github/actions/parse-manifest/defaults/database.yml`
- Create: `.github/actions/parse-manifest/defaults/storage.yml`
- Create: `tests/golden/minimal.dev.json`
- Create: `tests/golden/full.dev.json`
- Create: `tests/golden/full.prod.json`
- Test: `tests/parse_manifest.bats`

**Interfaces:**

- Consumes: `terraform/schema/cloud-tool.schema.json` (Task 1), fixtures `minimal.yml` / `full.yml` (Task 1).
- Produces: `parse-manifest.sh <manifest> <out-dir> [app-root]` writing `<out-dir>/tool.<env>.json` per environment plus key=value lines (`name`, `type`, `environments` as compact JSON array, `docker` as `true|false`) appended to `$GITHUB_OUTPUT` or `<out-dir>/outputs.txt`. Task 3 wraps this script; Task 4 consumes `tool.<env>.json`.

- [ ] **Step 1: Write golden files**

`tests/golden/minimal.dev.json`:

```json
{
  "name": "orders-api",
  "type": "container-app",
  "app": {
    "port": 8080,
    "ingress": "internal",
    "cpu": 0.5,
    "memory": "1Gi",
    "replicas": { "min": 1, "max": 3 },
    "env": {},
    "secrets": []
  }
}
```

`tests/golden/full.dev.json`:

```json
{
  "name": "orders-api",
  "type": "container-app",
  "app": {
    "port": 8080,
    "ingress": "internal",
    "cpu": 0.5,
    "memory": "1Gi",
    "replicas": { "min": 1, "max": 3 },
    "docker": { "file": "./Dockerfile", "context": "." },
    "env": { "LOG_LEVEL": "info" },
    "secrets": ["STRIPE_KEY"]
  },
  "database": { "size": "small", "storage_gb": 32, "public_access": false },
  "storage": { "containers": ["uploads"], "public_access": false }
}
```

`tests/golden/full.prod.json`:

```json
{
  "name": "orders-api",
  "type": "container-app",
  "app": {
    "port": 8080,
    "ingress": "internal",
    "cpu": 0.5,
    "memory": "1Gi",
    "replicas": { "min": 2, "max": 10 },
    "docker": { "file": "./Dockerfile", "context": "." },
    "env": { "LOG_LEVEL": "warn" },
    "secrets": ["STRIPE_KEY"]
  },
  "database": { "size": "medium", "storage_gb": 32, "public_access": false },
  "storage": { "containers": ["uploads"], "public_access": false }
}
```

- [ ] **Step 2: Write the failing test**

`tests/parse_manifest.bats`:

```bash
#!/usr/bin/env bats

setup() {
  REPO_ROOT="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"
  SCRIPT="$REPO_ROOT/.github/actions/parse-manifest/parse-manifest.sh"
  FIXTURES="$REPO_ROOT/tests/fixtures/manifests"
  GOLDEN="$REPO_ROOT/tests/golden"
  TMP="$(mktemp -d)"
}

teardown() { rm -rf "$TMP"; }

@test "minimal manifest produces dev tool.json matching golden" {
  run "$SCRIPT" "$FIXTURES/minimal.yml" "$TMP/out"
  [ "$status" -eq 0 ]
  diff <(jq -S . "$TMP/out/tool.dev.json") <(jq -S . "$GOLDEN/minimal.dev.json")
}

@test "full manifest produces dev tool.json (no overlay changes)" {
  run "$SCRIPT" "$FIXTURES/full.yml" "$TMP/out"
  [ "$status" -eq 0 ]
  diff <(jq -S . "$TMP/out/tool.dev.json") <(jq -S . "$GOLDEN/full.dev.json")
}

@test "full manifest produces prod tool.json with overlay applied" {
  run "$SCRIPT" "$FIXTURES/full.yml" "$TMP/out"
  [ "$status" -eq 0 ]
  diff <(jq -S . "$TMP/out/tool.prod.json") <(jq -S . "$GOLDEN/full.prod.json")
}

@test "invalid manifest fails before producing output" {
  run "$SCRIPT" "$FIXTURES/invalid-bad-type.yml" "$TMP/out"
  [ "$status" -ne 0 ]
  [ ! -f "$TMP/out/tool.dev.json" ]
}
```

- [ ] **Step 3: Run test to verify it fails**

Run: `bats tests/parse_manifest.bats`
Expected: all 4 FAIL (script does not exist).

- [ ] **Step 4: Write defaults files**

`.github/actions/parse-manifest/defaults/container-app.yml`:

```yaml
app:
  port: 8080
  ingress: internal
  cpu: 0.5
  memory: 1Gi
  replicas:
    min: 1
    max: 3
  env: {}
  secrets: []
```

`.github/actions/parse-manifest/defaults/function.yml`:

```yaml
app:
  ingress: internal
  env: {}
  secrets: []
```

`.github/actions/parse-manifest/defaults/static-site.yml`:

```yaml
app:
  env: {}
```

`.github/actions/parse-manifest/defaults/database.yml`:

```yaml
size: small
storage_gb: 32
public_access: false
```

`.github/actions/parse-manifest/defaults/storage.yml`:

```yaml
containers: []
public_access: false
```

- [ ] **Step 5: Write the script**

`.github/actions/parse-manifest/parse-manifest.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

# usage: parse-manifest.sh <manifest-path> <output-dir> [app-root]
MANIFEST="${1:?manifest path required}"
OUT="${2:?output dir required}"
APP_ROOT="${3:-.}"

ACTION_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$ACTION_DIR/../../.." && pwd)"
SCHEMA="$REPO_ROOT/terraform/schema/cloud-tool.schema.json"
DEFAULTS="$ACTION_DIR/defaults"

mkdir -p "$OUT"

yq -o=json '.' "$MANIFEST" > "$OUT/manifest.json"
npx --yes ajv-cli@5 validate --spec=draft2020 -s "$SCHEMA" -d "$OUT/manifest.json"

NAME="$(yq '.name' "$MANIFEST")"
TYPE="$(yq '.type' "$MANIFEST")"
ENVS="$(yq -o=json -I=0 '(.environments // {"dev": {}}) | keys' "$MANIFEST")"

DOCKER=false
if [ "$(yq '.app.docker' "$MANIFEST")" != "null" ] || [ -f "$APP_ROOT/Dockerfile" ]; then
  DOCKER=true
fi

yq 'del(.environments)' "$MANIFEST" > "$OUT/base.yml"

for env in $(echo "$ENVS" | yq -p=json '.[]'); do
  yq ".environments.\"$env\" // {}" "$MANIFEST" > "$OUT/overlay.$env.yml"
  yq eval-all '. as $item ireduce ({}; . * $item)' \
    "$DEFAULTS/$TYPE.yml" "$OUT/base.yml" "$OUT/overlay.$env.yml" > "$OUT/merged.$env.yml"

  for section in database storage; do
    if [ "$(yq ".$section" "$OUT/merged.$env.yml")" != "null" ]; then
      yq "{\"$section\": .}" "$DEFAULTS/$section.yml" > "$OUT/section-defaults.yml"
      yq eval-all '. as $item ireduce ({}; . * $item)' \
        "$OUT/section-defaults.yml" "$OUT/merged.$env.yml" > "$OUT/merged.$env.tmp.yml"
      mv "$OUT/merged.$env.tmp.yml" "$OUT/merged.$env.yml"
    fi
  done

  yq -o=json '.' "$OUT/merged.$env.yml" > "$OUT/tool.$env.json"
done

{
  echo "name=$NAME"
  echo "type=$TYPE"
  echo "environments=$ENVS"
  echo "docker=$DOCKER"
} >> "${GITHUB_OUTPUT:-$OUT/outputs.txt}"
```

Make it executable: `chmod +x .github/actions/parse-manifest/parse-manifest.sh`

- [ ] **Step 6: Run test to verify it passes**

Run: `bats tests/parse_manifest.bats`
Expected: 4 tests PASS. If a golden diff fails, inspect with `diff <(jq -S . <actual>) <(jq -S . <golden>)` — the merge order is defaults → base → overlay, later wins; arrays are replaced, maps deep-merged.

- [ ] **Step 7: Commit**

```bash
git add .github/actions/parse-manifest tests
git commit -m "feat: add parse-manifest merge script with preset defaults"
```

---

### Task 3: parse-manifest outputs + composite action wrapper

**Files:**

- Create: `.github/actions/parse-manifest/action.yml`
- Modify: `tests/parse_manifest.bats` (append output tests)

**Interfaces:**

- Consumes: `parse-manifest.sh` (Task 2).
- Produces: composite action `parse-manifest` with inputs `manifest` (default `.cloud-tool.yml`), `output-dir` (default `.cloud-tool`), `app-root` (default `.`); outputs `name`, `type`, `environments` (JSON array string), `docker` (`true`/`false`). Plan 3's workflow consumes these outputs.

- [ ] **Step 1: Write the failing tests (append to `tests/parse_manifest.bats`)**

```bash
@test "outputs file contains name, type, environments, docker" {
  run "$SCRIPT" "$FIXTURES/minimal.yml" "$TMP/out"
  [ "$status" -eq 0 ]
  grep -q '^name=orders-api$' "$TMP/out/outputs.txt"
  grep -q '^type=container-app$' "$TMP/out/outputs.txt"
  grep -q '^environments=\["dev"\]$' "$TMP/out/outputs.txt"
  grep -q '^docker=false$' "$TMP/out/outputs.txt"
}

@test "docker output true when Dockerfile exists in app root" {
  mkdir -p "$TMP/approot"
  touch "$TMP/approot/Dockerfile"
  run "$SCRIPT" "$FIXTURES/minimal.yml" "$TMP/out" "$TMP/approot"
  [ "$status" -eq 0 ]
  grep -q '^docker=true$' "$TMP/out/outputs.txt"
}

@test "docker output true when manifest has docker section" {
  run "$SCRIPT" "$FIXTURES/full.yml" "$TMP/out"
  [ "$status" -eq 0 ]
  grep -q '^docker=true$' "$TMP/out/outputs.txt"
}

@test "environments output lists manifest env keys" {
  run "$SCRIPT" "$FIXTURES/full.yml" "$TMP/out"
  [ "$status" -eq 0 ]
  grep -q '^environments=\["dev","prod"\]$' "$TMP/out/outputs.txt"
}
```

- [ ] **Step 2: Run tests**

Run: `bats tests/parse_manifest.bats`
Expected: PASS already (Task 2's script writes outputs). If any fail, fix the script — the tests are the contract.

- [ ] **Step 3: Write the composite action**

`.github/actions/parse-manifest/action.yml`:

```yaml
name: parse-manifest
description: Validate .cloud-tool.yml against the schema and merge per-environment tool config
inputs:
  manifest:
    description: Path to the manifest in the app repo
    default: .cloud-tool.yml
  output-dir:
    description: Directory to write merged per-environment tool JSON files
    default: .cloud-tool
  app-root:
    description: App repo root, used for Dockerfile detection
    default: "."
outputs:
  name:
    description: Tool name
    value: ${{ steps.parse.outputs.name }}
  type:
    description: Tool type (preset)
    value: ${{ steps.parse.outputs.type }}
  environments:
    description: JSON array of environment names
    value: ${{ steps.parse.outputs.environments }}
  docker:
    description: Whether a docker image build is required (true/false)
    value: ${{ steps.parse.outputs.docker }}
runs:
  using: composite
  steps:
    - id: parse
      shell: bash
      run: >-
        "${{ github.action_path }}/parse-manifest.sh"
        "${{ inputs.manifest }}"
        "${{ inputs.output-dir }}"
        "${{ inputs.app-root }}"
```

- [ ] **Step 4: Lint the action**

Run: `brew install actionlint 2>/dev/null; actionlint` (actionlint scans `.github` automatically; composite actions are checked when referenced — at minimum it must parse: `yq '.' .github/actions/parse-manifest/action.yml > /dev/null`)
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add .github/actions/parse-manifest tests
git commit -m "feat: add parse-manifest composite action wrapper and output tests"
```

---

### Task 4: Platform environment configs + resolve-config script

**Files:**

- Create: `environments/dev.yml`
- Create: `environments/staging.yml`
- Create: `environments/prod.yml`
- Create: `.github/actions/resolve-config/resolve-config.sh`
- Create: `tests/golden/tfvars.minimal.dev.json`
- Test: `tests/resolve_config.bats`

**Interfaces:**

- Consumes: `tool.<env>.json` produced by `parse-manifest.sh` (Task 2).
- Produces: `resolve-config.sh <tool-json> <platform-env-yml> <env-name> <out-file>` writing tfvars JSON shaped `{ "config": { ...tool fields, "environment": "<env>", "platform": { ...platform yml } } }`. Plan 2's Terraform root module reads exactly this shape via `-var-file`.

- [ ] **Step 1: Write platform env config examples**

`environments/dev.yml` (values are examples for the sandbox subscription; edit per real landing zone):

```yaml
subscription_id: 00000000-0000-0000-0000-000000000000
tenant_id: 00000000-0000-0000-0000-000000000000
location: eastus2
naming_prefix: ""
network:
  vnet_id: /subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-network-dev/providers/Microsoft.Network/virtualNetworks/vnet-spoke-dev
  subnets:
    container_apps: /subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-network-dev/providers/Microsoft.Network/virtualNetworks/vnet-spoke-dev/subnets/snet-aca
    private_endpoints: /subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-network-dev/providers/Microsoft.Network/virtualNetworks/vnet-spoke-dev/subnets/snet-pe
    functions: /subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-network-dev/providers/Microsoft.Network/virtualNetworks/vnet-spoke-dev/subnets/snet-func
  private_dns_zone_ids:
    postgres: /subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-dns/providers/Microsoft.Network/privateDnsZones/privatelink.postgres.database.azure.com
    blob: /subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-dns/providers/Microsoft.Network/privateDnsZones/privatelink.blob.core.windows.net
    keyvault: /subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-dns/providers/Microsoft.Network/privateDnsZones/privatelink.vaultcore.azure.net
acr:
  login_server: acrplatformdev.azurecr.io
  resource_group: rg-platform-dev
terraform_state:
  resource_group: rg-tfstate
  storage_account: sttfstatedev
  container: tfstate
deploy:
  client_id: 00000000-0000-0000-0000-000000000000
runner_access: public-allowlist
```

`environments/staging.yml` and `environments/prod.yml`: same structure — copy `dev.yml`, replace every `-dev`/`dev` suffix with `-staging`/`staging` and `-prod`/`prod` respectively (`vnet-spoke-staging`, `acrplatformstaging.azurecr.io`, `sttfstatestaging`, …). For `prod.yml` set `runner_access: private`.

- [ ] **Step 2: Write golden file**

`tests/golden/tfvars.minimal.dev.json` — the minimal tool.dev.json wrapped with environment + platform (platform block mirrors `environments/dev.yml` exactly):

```json
{
  "config": {
    "name": "orders-api",
    "type": "container-app",
    "environment": "dev",
    "app": {
      "port": 8080,
      "ingress": "internal",
      "cpu": 0.5,
      "memory": "1Gi",
      "replicas": { "min": 1, "max": 3 },
      "env": {},
      "secrets": []
    },
    "platform": {
      "subscription_id": "00000000-0000-0000-0000-000000000000",
      "tenant_id": "00000000-0000-0000-0000-000000000000",
      "location": "eastus2",
      "naming_prefix": "",
      "network": {
        "vnet_id": "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-network-dev/providers/Microsoft.Network/virtualNetworks/vnet-spoke-dev",
        "subnets": {
          "container_apps": "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-network-dev/providers/Microsoft.Network/virtualNetworks/vnet-spoke-dev/subnets/snet-aca",
          "private_endpoints": "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-network-dev/providers/Microsoft.Network/virtualNetworks/vnet-spoke-dev/subnets/snet-pe",
          "functions": "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-network-dev/providers/Microsoft.Network/virtualNetworks/vnet-spoke-dev/subnets/snet-func"
        },
        "private_dns_zone_ids": {
          "postgres": "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-dns/providers/Microsoft.Network/privateDnsZones/privatelink.postgres.database.azure.com",
          "blob": "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-dns/providers/Microsoft.Network/privateDnsZones/privatelink.blob.core.windows.net",
          "keyvault": "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-dns/providers/Microsoft.Network/privateDnsZones/privatelink.vaultcore.azure.net"
        }
      },
      "acr": {
        "login_server": "acrplatformdev.azurecr.io",
        "resource_group": "rg-platform-dev"
      },
      "terraform_state": {
        "resource_group": "rg-tfstate",
        "storage_account": "sttfstatedev",
        "container": "tfstate"
      },
      "deploy": { "client_id": "00000000-0000-0000-0000-000000000000" },
      "runner_access": "public-allowlist"
    }
  }
}
```

- [ ] **Step 3: Write the failing test**

`tests/resolve_config.bats`:

```bash
#!/usr/bin/env bats

setup() {
  REPO_ROOT="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"
  PARSE="$REPO_ROOT/.github/actions/parse-manifest/parse-manifest.sh"
  RESOLVE="$REPO_ROOT/.github/actions/resolve-config/resolve-config.sh"
  FIXTURES="$REPO_ROOT/tests/fixtures/manifests"
  GOLDEN="$REPO_ROOT/tests/golden"
  ENVDIR="$REPO_ROOT/environments"
  TMP="$(mktemp -d)"
}

teardown() { rm -rf "$TMP"; }

@test "minimal dev tool.json + dev platform config produces golden tfvars" {
  "$PARSE" "$FIXTURES/minimal.yml" "$TMP/out"
  run "$RESOLVE" "$TMP/out/tool.dev.json" "$ENVDIR/dev.yml" dev "$TMP/out/tfvars.dev.json"
  [ "$status" -eq 0 ]
  diff <(jq -S . "$TMP/out/tfvars.dev.json") <(jq -S . "$GOLDEN/tfvars.minimal.dev.json")
}

@test "missing platform env file fails with clear message" {
  "$PARSE" "$FIXTURES/minimal.yml" "$TMP/out"
  run "$RESOLVE" "$TMP/out/tool.dev.json" "$ENVDIR/nonexistent.yml" nonexistent "$TMP/out/tfvars.json"
  [ "$status" -ne 0 ]
  [[ "$output" == *"platform config not found"* ]]
}
```

- [ ] **Step 4: Run test to verify it fails**

Run: `bats tests/resolve_config.bats`
Expected: both FAIL (resolve-config.sh does not exist).

- [ ] **Step 5: Write the script**

`.github/actions/resolve-config/resolve-config.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

# usage: resolve-config.sh <tool-json> <platform-env-yml> <env-name> <out-file>
TOOL="${1:?tool json required}"
PLATFORM_FILE="${2:?platform env yml required}"
ENV_NAME="${3:?environment name required}"
OUT_FILE="${4:?output file required}"

if [ ! -f "$PLATFORM_FILE" ]; then
  echo "error: platform config not found: $PLATFORM_FILE (environment '$ENV_NAME' has no platform config file)" >&2
  exit 1
fi

PLATFORM_JSON="$(yq -o=json '.' "$PLATFORM_FILE")"
jq --argjson platform "$PLATFORM_JSON" --arg env "$ENV_NAME" \
  '{config: (. + {environment: $env, platform: $platform})}' \
  "$TOOL" > "$OUT_FILE"
```

Make it executable: `chmod +x .github/actions/resolve-config/resolve-config.sh`

- [ ] **Step 6: Run test to verify it passes**

Run: `bats tests/resolve_config.bats`
Expected: 2 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add environments .github/actions/resolve-config tests
git commit -m "feat: add platform env configs and resolve-config script"
```

---

### Task 5: resolve-config composite action

**Files:**

- Create: `.github/actions/resolve-config/action.yml`

**Interfaces:**

- Consumes: `resolve-config.sh` (Task 4).
- Produces: composite action `resolve-config` with inputs `tool-json`, `environment`, `platform-config-dir` (default `environments`), `out-file`; output `tfvars-file` (path). Plan 3's deploy job calls this before `terraform-deploy`.

- [ ] **Step 1: Write the composite action**

`.github/actions/resolve-config/action.yml`:

```yaml
name: resolve-config
description: Merge per-environment tool config with platform environment config into tfvars.json
inputs:
  tool-json:
    description: Path to tool.<env>.json produced by parse-manifest
    required: true
  environment:
    description: Environment name
    required: true
  platform-config-dir:
    description: Directory in the deploy repo containing <env>.yml platform configs
    default: environments
  out-file:
    description: Path to write the tfvars JSON file
    default: tfvars.json
outputs:
  tfvars-file:
    description: Path of the written tfvars JSON file
    value: ${{ inputs.out-file }}
runs:
  using: composite
  steps:
    - shell: bash
      run: >-
        "${{ github.action_path }}/resolve-config.sh"
        "${{ inputs.tool-json }}"
        "${{ inputs.platform-config-dir }}/${{ inputs.environment }}.yml"
        "${{ inputs.environment }}"
        "${{ inputs.out-file }}"
```

- [ ] **Step 2: Verify it parses**

Run: `yq '.' .github/actions/resolve-config/action.yml > /dev/null && actionlint`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add .github/actions/resolve-config
git commit -m "feat: add resolve-config composite action wrapper"
```

---

### Task 6: CI workflow

**Files:**

- Create: `.github/workflows/ci.yml`

**Interfaces:**

- Consumes: `tests/*.bats` (Tasks 1–4).
- Produces: CI running bats + actionlint on every PR and push to main; the repo's quality gate for Plans 2–3.

- [ ] **Step 1: Write the workflow**

`.github/workflows/ci.yml`:

```yaml
name: ci
on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install bats
        run: npm install -g bats

      - name: Run tests
        run: bats tests/

      - name: Lint workflows
        run: |
          curl -sSL https://github.com/rhysd/actionlint/releases/download/v1.7.7/actionlint_1.7.7_linux_amd64.tar.gz | tar xz actionlint
          ./actionlint -color
```

Note: `yq`, `jq`, and Node are preinstalled on `ubuntu-latest` runners.

- [ ] **Step 2: Verify locally**

Run: `actionlint && bats tests/`
Expected: actionlint clean; all bats tests PASS (Tasks 1–4: 15 tests total).

- [ ] **Step 3: Commit and push**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: run bats tests and actionlint on PRs and main"
git push
```

- [ ] **Step 4: Verify CI run passes**

Run: `gh run watch --exit-status "$(gh run list --workflow ci --limit 1 --json databaseId --jq '.[0].databaseId')"`
Expected: run completes with success. If it fails on tool availability (yq/bats), fix the install steps in `ci.yml` before proceeding.

---

## Self-Review Notes

- Spec coverage (this plan's slice): manifest schema ✔ (Task 1), defaults + merge order ✔ (Task 2), parse-manifest action + outputs ✔ (Task 3), platform env configs + resolve-config ✔ (Tasks 4–5), CI ✔ (Task 6). Terraform, workflow, docker-build, sync-secrets, terraform-deploy are Plans 2–3 by design.
- tfvars shape `{config: {…, environment, platform}}` is the contract Plan 2's root module must honor.
- parse-manifest output contract (`name`, `type`, `environments` JSON array, `docker`) is the contract Plan 3's workflow must honor.
