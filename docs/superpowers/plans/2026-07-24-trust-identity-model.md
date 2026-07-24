# Trust & Identity Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the three-tier identity model (bootstrap/plan/apply managed identities), Azure Blob + AWS S3 state backends over OIDC, and self/delegated trust modes, with the security-critical logic (backend rendering, federation-subject resolution, login sequencing) as pure Python and the identity provisioning as Terraform bootstrap stacks — all offline-testable.

**Architecture:** New `cloudapp` modules turn (platform config, event, mode) into the ordered sequence of OIDC logins and the exact federation subjects, unit-tested with no cloud. Two new Terraform roots — a manual per-subscription `bootstrap/` and an automated per-tool `terraform/bootstrap/` — provision the identities, tested with `terraform test` mock providers. `deploy.yml` is rewired to run the event-gated login handoff.

**Tech Stack:** Python 3.9+ (stdlib + PyYAML), pytest; Terraform ≥1.9, azurerm ~>4.0; GitHub Actions (`azure/login`, `aws-actions/configure-aws-credentials`, `repository_dispatch`).

**Spec:** `docs/superpowers/specs/2026-07-24-trust-identity-model-design.md`

## Global Constraints

- Package is `cloudapp` (post-rename). Manifest is `.cloud-app.yml`. Schema at `terraform/schema/cloud-app.schema.json`.
- Identity naming: shared `id-cloudapp-bootstrap-<env>`; per-tool `id-<tool>-<env>-plan` (RG Reader + Storage Blob Data Reader + Key Vault Reader), `id-<tool>-<env>-apply` (RG Contributor). Custom role `cloudapp-bootstrap`.
- Bootstrap custom role actions, EXACTLY these, no wildcard: `Microsoft.Resources/subscriptions/resourceGroups/read`, `.../write`, `Microsoft.ManagedIdentity/userAssignedIdentities/read`, `.../write`, `Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials/write`, `Microsoft.Authorization/roleAssignments/read`, `.../write`.
- Two state files per tool+env: `<tool>/<env>.bootstrap.tfstate` (writer: bootstrap MI) and `<tool>/<env>.tfstate` (reader: plan MI, writer: apply MI).
- Federation subjects (mode → MI → subject) per the spec table; delegated mode NEVER yields an app-repo subject.
- `mode` default is `delegated`. Trust `mode` is a workflow input, not manifest.
- State backend: `azurerm` (existing) or `s3`; S3 uses `AssumeRoleWithWebIdentity` into `role_arn`; an S3 run does two OIDC logins (AWS for state, Azure for resources).
- Event gating: PR → plan MI only; default branch → bootstrap MI, then plan MI, then apply MI.
- All new pure logic in `cloudapp/` is unit-tested; Terraform via `terraform test` mock providers; `terraform fmt -check` + tflint clean; actionlint clean; pytest coverage stays ≥90%.
- Backward compatibility: platform config migrates `terraform_state:` → `state_backend: {type: azurerm, ...}`; update all `environments/*.yml` and `tests/fixtures/environments/dev.yml`.

## File Structure

```
cloudapp/
├── backend.py         # MODIFY: state_backend (azurerm|s3) + stack (bootstrap|main)
├── identity.py        # NEW: federation subjects + login sequencing
├── dispatch.py        # NEW: delegated repository_dispatch payload + allowlist
├── cli.py             # MODIFY: plan-identity / subjects subcommands
terraform/
├── bootstrap/         # NEW per-tool: RG + plan/apply MIs + roles + fed creds
│   ├── versions.tf  variables.tf  main.tf  outputs.tf
│   └── tests/bootstrap.tftest.hcl
bootstrap/             # NEW manual per-subscription: custom role + bootstrap MI
│   ├── versions.tf  variables.tf  main.tf  outputs.tf  README.md
│   └── tests/root.tftest.hcl
tests/py/
├── test_backend.py    # MODIFY
├── test_identity.py   # NEW
└── test_dispatch.py   # NEW
environments/*.yml     # MODIFY: state_backend block
```

---

### Task 1: State backend rendering — azurerm + s3, bootstrap + main stacks

**Files:**

- Modify: `cloudapp/backend.py`
- Modify: `tests/py/test_backend.py`
- Modify: `environments/dev.yml`, `environments/staging.yml`, `environments/prod.yml`, `tests/fixtures/environments/dev.yml`

**Interfaces:**

- Consumes: platform config `state_backend` block.
- Produces: `render(platform_path, name, env, stack="main") -> list[str]` (backend-config lines); `state_key(name, env, stack) -> str`; `backend_type(platform_path) -> str`. `stack` is `"main"` or `"bootstrap"`.

- [ ] **Step 1: Migrate the platform fixtures to `state_backend`**

In each `environments/*.yml` and `tests/fixtures/environments/dev.yml`, replace the `terraform_state:` block with (dev shown; suffix per env):

```yaml
state_backend:
  type: azurerm
  resource_group: rg-tfstate
  storage_account: sttfstatedev
  container: tfstate
```

- [ ] **Step 2: Write the failing tests** (`tests/py/test_backend.py`, replacing the existing two)

```python
import pytest

from cloudapp import backend
from conftest import ENVDIR


def test_azurerm_main_backend_lines():
    lines = backend.render(ENVDIR / "dev.yml", "orders-api", "dev", stack="main")
    assert lines == [
        "resource_group_name=rg-tfstate",
        "storage_account_name=sttfstatedev",
        "container_name=tfstate",
        "key=orders-api/dev.tfstate",
        "use_oidc=true",
        "use_azuread_auth=true",
    ]


def test_azurerm_bootstrap_stack_uses_bootstrap_key():
    lines = backend.render(ENVDIR / "dev.yml", "orders-api", "dev", stack="bootstrap")
    assert "key=orders-api/dev.bootstrap.tfstate" in lines


def test_s3_backend_lines(tmp_path):
    (tmp_path / "prod.yml").write_text(
        "state_backend:\n"
        "  type: s3\n"
        "  bucket: my-tfstate\n"
        "  region: us-east-1\n"
        "  dynamodb_table: tfstate-locks\n"
        "  role_arn: arn:aws:iam::123456789012:role/gha-tfstate\n"
    )
    lines = backend.render(tmp_path / "prod.yml", "orders-api", "prod", stack="main")
    assert lines == [
        "bucket=my-tfstate",
        "key=orders-api/prod.tfstate",
        "region=us-east-1",
        "dynamodb_table=tfstate-locks",
        "role_arn=arn:aws:iam::123456789012:role/gha-tfstate",
        "encrypt=true",
    ]


def test_backend_type_reports_configured_type():
    assert backend.backend_type(ENVDIR / "dev.yml") == "azurerm"


def test_unknown_backend_type_fails(tmp_path):
    (tmp_path / "x.yml").write_text("state_backend:\n  type: gcs\n")
    with pytest.raises(backend.BackendError, match="unknown state backend"):
        backend.render(tmp_path / "x.yml", "n", "dev")


def test_missing_azurerm_key_fails(tmp_path):
    (tmp_path / "x.yml").write_text("state_backend:\n  type: azurerm\n  container: tfstate\n")
    with pytest.raises(backend.BackendError, match="storage_account"):
        backend.render(tmp_path / "x.yml", "n", "dev")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python3 -m pytest tests/py/test_backend.py -q`
Expected: FAIL (`render()` has no `stack`/type support).

- [ ] **Step 4: Rewrite `cloudapp/backend.py`**

```python
"""Terraform backend configuration (azurerm or s3) from platform config."""

from pathlib import Path

from .yamlcompat import load_yaml


class BackendError(Exception):
    pass


def _config(platform_path):
    platform = load_yaml(Path(platform_path).read_text()) or {}
    sb = platform.get("state_backend")
    if not sb or not sb.get("type"):
        raise BackendError(f"state_backend.type missing in {platform_path}")
    return sb


def backend_type(platform_path):
    return _config(platform_path)["type"]


def state_key(name, env, stack="main"):
    suffix = "bootstrap.tfstate" if stack == "bootstrap" else "tfstate"
    return f"{name}/{env}.{suffix}"


def render(platform_path, name, env, stack="main"):
    """-backend-config key=value lines for one tool + environment + stack."""
    sb = _config(platform_path)
    key = state_key(name, env, stack)
    if sb["type"] == "azurerm":
        for field in ("resource_group", "storage_account", "container"):
            if not sb.get(field):
                raise BackendError(f"state_backend.{field} missing in {platform_path}")
        return [
            f"resource_group_name={sb['resource_group']}",
            f"storage_account_name={sb['storage_account']}",
            f"container_name={sb['container']}",
            f"key={key}",
            "use_oidc=true",
            "use_azuread_auth=true",
        ]
    if sb["type"] == "s3":
        for field in ("bucket", "region", "role_arn"):
            if not sb.get(field):
                raise BackendError(f"state_backend.{field} missing in {platform_path}")
        lines = [
            f"bucket={sb['bucket']}",
            f"key={key}",
            f"region={sb['region']}",
        ]
        if sb.get("dynamodb_table"):
            lines.append(f"dynamodb_table={sb['dynamodb_table']}")
        lines += [f"role_arn={sb['role_arn']}", "encrypt=true"]
        return lines
    raise BackendError(f"unknown state backend type '{sb['type']}' in {platform_path}")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/py/test_backend.py -q`
Expected: PASS (6 tests).

- [ ] **Step 6: Regenerate terraform fixtures + full suite** (the tfvars carry the platform block, now with `state_backend`)

Run: `python3 scripts/generate_tf_fixtures.py && python3 -m pytest tests/py -q --cov=cloudapp --cov-fail-under=90`
Expected: PASS. Then `terraform -chdir=terraform test` — 11 PASS (platform block shape change is inert to the module).

- [ ] **Step 7: Commit**

```bash
git add cloudapp/backend.py tests/py/test_backend.py environments tests/fixtures/environments terraform/tests/fixtures
git commit -m "feat(cloudapp): state_backend rendering for azurerm and s3, bootstrap vs main stack keys"
```

---

### Task 2: Federation subject resolution

**Files:**

- Create: `cloudapp/identity.py`
- Create: `tests/py/test_identity.py`

**Interfaces:**

- Consumes: nothing.
- Produces: `federation_subjects(mi, mode, app_repo, central_repo, env) -> list[str]` where `mi` in `{"plan","apply"}`; and constant `CENTRAL_REPO`. (Bootstrap MI subject is set at manual bootstrap time, out of scope here.)

- [ ] **Step 1: Write the failing tests** (`tests/py/test_identity.py`)

```python
import pytest

from cloudapp import identity


def test_self_mode_plan_subjects_reference_app_repo():
    subs = identity.federation_subjects(
        "plan", "self", app_repo="acme/orders", central_repo="vgmello/deploy", env="prod"
    )
    assert subs == [
        "repo:acme/orders:pull_request",
        "repo:acme/orders:environment:prod",
    ]


def test_self_mode_apply_subject_is_environment_only():
    subs = identity.federation_subjects(
        "apply", "self", app_repo="acme/orders", central_repo="vgmello/deploy", env="prod"
    )
    assert subs == ["repo:acme/orders:environment:prod"]


def test_delegated_mode_plan_uses_central_plan_environment():
    subs = identity.federation_subjects(
        "plan", "delegated", app_repo="acme/orders", central_repo="vgmello/deploy", env="prod"
    )
    assert subs == ["repo:vgmello/deploy:environment:prod-plan"]


def test_delegated_mode_apply_uses_central_environment():
    subs = identity.federation_subjects(
        "apply", "delegated", app_repo="acme/orders", central_repo="vgmello/deploy", env="prod"
    )
    assert subs == ["repo:vgmello/deploy:environment:prod"]


def test_delegated_mode_never_references_app_repo():
    for mi in ("plan", "apply"):
        subs = identity.federation_subjects(
            mi, "delegated", app_repo="acme/orders", central_repo="vgmello/deploy", env="prod"
        )
        assert all("acme/orders" not in s for s in subs)


def test_unknown_mode_or_mi_fails():
    with pytest.raises(ValueError):
        identity.federation_subjects("plan", "trustme", "a/b", "c/d", "dev")
    with pytest.raises(ValueError):
        identity.federation_subjects("bootstrap", "self", "a/b", "c/d", "dev")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/py/test_identity.py -q`
Expected: FAIL (`identity` missing).

- [ ] **Step 3: Implement `cloudapp/identity.py`** (subject half only)

```python
"""Deploy identity model: federation subjects and login sequencing.

Pure functions — the security-critical mapping from (event, mode) to which
managed identity signs in for which phase, and to the OIDC subject each
identity's federated credential must trust.
"""

MODES = ("self", "delegated")
DEPLOY_IDENTITIES = ("plan", "apply")


def federation_subjects(mi, mode, app_repo, central_repo, env):
    """OIDC subjects a per-tool MI's federated credentials must trust."""
    if mode not in MODES:
        raise ValueError(f"unknown mode '{mode}'")
    if mi not in DEPLOY_IDENTITIES:
        raise ValueError(f"unknown deploy identity '{mi}'")

    if mode == "self":
        if mi == "plan":
            return [f"repo:{app_repo}:pull_request", f"repo:{app_repo}:environment:{env}"]
        return [f"repo:{app_repo}:environment:{env}"]
    # delegated: only the central repo's subjects, never the app repo
    if mi == "plan":
        return [f"repo:{central_repo}:environment:{env}-plan"]
    return [f"repo:{central_repo}:environment:{env}"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/py/test_identity.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add cloudapp/identity.py tests/py/test_identity.py
git commit -m "feat(cloudapp): federation subject resolution for self/delegated modes"
```

---

### Task 3: Login sequencing (event × mode × backend → ordered phases)

**Files:**

- Modify: `cloudapp/identity.py`
- Modify: `tests/py/test_identity.py`

**Interfaces:**

- Consumes: `backend.backend_type`.
- Produces: `login_plan(event, backend_type) -> list[dict]`. Each phase dict: `{"identity": "bootstrap"|"plan"|"apply", "action": "apply"|"plan", "stack": "bootstrap"|"main", "state_login": bool}`. `event` is `"pull_request"` or `"default_branch"`.

- [ ] **Step 1: Write the failing tests** (append to `tests/py/test_identity.py`)

```python
def test_pr_event_is_plan_only():
    phases = identity.login_plan("pull_request", "azurerm")
    assert phases == [
        {"identity": "plan", "action": "plan", "stack": "main", "state_login": False},
    ]


def test_default_branch_runs_bootstrap_plan_apply():
    phases = identity.login_plan("default_branch", "azurerm")
    assert [p["identity"] for p in phases] == ["bootstrap", "plan", "apply"]
    assert [p["action"] for p in phases] == ["apply", "plan", "apply"]
    assert [p["stack"] for p in phases] == ["bootstrap", "main", "main"]


def test_s3_backend_marks_every_phase_for_aws_state_login():
    for event in ("pull_request", "default_branch"):
        phases = identity.login_plan(event, "s3")
        assert all(p["state_login"] for p in phases)
    # azurerm backend needs no separate state login
    assert all(not p["state_login"] for p in identity.login_plan("default_branch", "azurerm"))


def test_unknown_event_fails():
    with pytest.raises(ValueError):
        identity.login_plan("tag_push", "azurerm")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/py/test_identity.py -q`
Expected: FAIL (`login_plan` missing).

- [ ] **Step 3: Add `login_plan` to `cloudapp/identity.py`**

```python
EVENTS = ("pull_request", "default_branch")


def login_plan(event, backend_type):
    """Ordered deploy phases for an event. Each phase names the identity that
    signs in, the terraform action, the stack, and whether the state backend
    needs its own (AWS) OIDC login this phase."""
    if event not in EVENTS:
        raise ValueError(f"unknown event '{event}'")
    state_login = backend_type == "s3"

    if event == "pull_request":
        phases = [{"identity": "plan", "action": "plan", "stack": "main"}]
    else:
        phases = [
            {"identity": "bootstrap", "action": "apply", "stack": "bootstrap"},
            {"identity": "plan", "action": "plan", "stack": "main"},
            {"identity": "apply", "action": "apply", "stack": "main"},
        ]
    for p in phases:
        p["state_login"] = state_login
    return phases
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/py/test_identity.py -q`
Expected: PASS (10 tests total in file).

- [ ] **Step 5: Commit**

```bash
git add cloudapp/identity.py tests/py/test_identity.py
git commit -m "feat(cloudapp): event-gated login sequencing with s3 state-login flag"
```

---

### Task 4: Delegated-mode dispatch payload + allowlist

**Files:**

- Create: `cloudapp/dispatch.py`
- Create: `tests/py/test_dispatch.py`

**Interfaces:**

- Consumes: nothing.
- Produces: `dispatch_payload(app_repo, sha, manifest, environment=None) -> dict`; `authorize(app_repo, allowlist) -> str` returning the mapped environment set, raising `DispatchError` when the repo is not allowlisted.

- [ ] **Step 1: Write the failing tests** (`tests/py/test_dispatch.py`)

```python
import pytest

from cloudapp import dispatch


def test_payload_shape():
    p = dispatch.dispatch_payload("acme/orders", "abc123", ".cloud-app.yml")
    assert p == {
        "event_type": "cloudapp-deploy",
        "client_payload": {
            "app_repo": "acme/orders",
            "sha": "abc123",
            "manifest": ".cloud-app.yml",
            "environment": "",
        },
    }


def test_payload_carries_single_environment_filter():
    p = dispatch.dispatch_payload("acme/orders", "abc123", ".cloud-app.yml", environment="dev")
    assert p["client_payload"]["environment"] == "dev"


def test_authorize_returns_mapped_environments():
    allowlist = {"acme/orders": ["dev", "prod"]}
    assert dispatch.authorize("acme/orders", allowlist) == ["dev", "prod"]


def test_authorize_rejects_unlisted_repo():
    with pytest.raises(dispatch.DispatchError, match="not authorized"):
        dispatch.authorize("evil/repo", {"acme/orders": ["dev"]})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/py/test_dispatch.py -q`
Expected: FAIL (`dispatch` missing).

- [ ] **Step 3: Implement `cloudapp/dispatch.py`**

```python
"""Delegated-mode dispatch: app repo -> central repo repository_dispatch."""

EVENT_TYPE = "cloudapp-deploy"


class DispatchError(Exception):
    pass


def dispatch_payload(app_repo, sha, manifest, environment=None):
    return {
        "event_type": EVENT_TYPE,
        "client_payload": {
            "app_repo": app_repo,
            "sha": sha,
            "manifest": manifest,
            "environment": environment or "",
        },
    }


def authorize(app_repo, allowlist):
    """Return the environments an app repo may deploy, or raise if unlisted."""
    if app_repo not in allowlist:
        raise DispatchError(f"repo '{app_repo}' is not authorized to deploy")
    return allowlist[app_repo]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/py/test_dispatch.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add cloudapp/dispatch.py tests/py/test_dispatch.py
git commit -m "feat(cloudapp): delegated dispatch payload and app-repo allowlist"
```

---

### Task 5: Manual per-subscription bootstrap stack (custom role + bootstrap MI)

**Files:**

- Create: `bootstrap/versions.tf`, `bootstrap/variables.tf`, `bootstrap/main.tf`, `bootstrap/outputs.tf`, `bootstrap/README.md`
- Create: `bootstrap/tests/root.tftest.hcl`

**Interfaces:**

- Consumes: nothing (root stack).
- Produces: outputs `bootstrap_identity_client_id`, `bootstrap_identity_principal_id`, `custom_role_id`.

- [ ] **Step 1: Write the module**

`bootstrap/versions.tf`:

```hcl
terraform {
  required_version = ">= 1.9.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}
```

`bootstrap/variables.tf`:

```hcl
variable "subscription_id" { type = string }
variable "location" { type = string }
variable "environment" { type = string }

variable "trusted_repo" {
  description = "owner/name of the repo whose environment subject the bootstrap identity trusts"
  type        = string
}
```

`bootstrap/main.tf`:

```hcl
provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
}

locals {
  scope = "/subscriptions/${var.subscription_id}"
}

resource "azurerm_role_definition" "bootstrap" {
  name        = "cloudapp-bootstrap"
  scope       = local.scope
  description = "Create resource groups, user-assigned identities, and role assignments only"

  permissions {
    actions = [
      "Microsoft.Resources/subscriptions/resourceGroups/read",
      "Microsoft.Resources/subscriptions/resourceGroups/write",
      "Microsoft.ManagedIdentity/userAssignedIdentities/read",
      "Microsoft.ManagedIdentity/userAssignedIdentities/write",
      "Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials/write",
      "Microsoft.Authorization/roleAssignments/read",
      "Microsoft.Authorization/roleAssignments/write",
    ]
    not_actions = []
  }

  assignable_scopes = [local.scope]
}

resource "azurerm_resource_group" "identities" {
  name     = "rg-cloudapp-identities-${var.environment}"
  location = var.location
}

resource "azurerm_user_assigned_identity" "bootstrap" {
  name                = "id-cloudapp-bootstrap-${var.environment}"
  location            = var.location
  resource_group_name = azurerm_resource_group.identities.name
}

resource "azurerm_role_assignment" "bootstrap" {
  scope              = local.scope
  role_definition_id = azurerm_role_definition.bootstrap.role_definition_resource_id
  principal_id       = azurerm_user_assigned_identity.bootstrap.principal_id
}

resource "azurerm_federated_identity_credential" "bootstrap" {
  name                = "gha-${var.environment}"
  resource_group_name = azurerm_resource_group.identities.name
  parent_id           = azurerm_user_assigned_identity.bootstrap.id
  audience            = ["api://AzureADTokenExchange"]
  issuer              = "https://token.actions.githubusercontent.com"
  subject             = "repo:${var.trusted_repo}:environment:${var.environment}"
}
```

`bootstrap/outputs.tf`:

```hcl
output "bootstrap_identity_client_id" {
  value = azurerm_user_assigned_identity.bootstrap.client_id
}

output "bootstrap_identity_principal_id" {
  value = azurerm_user_assigned_identity.bootstrap.principal_id
}

output "custom_role_id" {
  value = azurerm_role_definition.bootstrap.role_definition_resource_id
}
```

`bootstrap/README.md`:

````markdown
# Bootstrap (run once per subscription + environment)

A subscription **Owner** runs this stack one time per environment. It creates
the `cloudapp-bootstrap` custom role, the shared `id-cloudapp-bootstrap-<env>`
identity, its role assignment, and a federated credential trusting the trusted
repo's `environment:<env>` subject.

```bash
terraform -chdir=bootstrap init
terraform -chdir=bootstrap apply \
  -var subscription_id=<sub> -var location=eastus2 \
  -var environment=dev -var trusted_repo=vgmello/deploy
```
````

Record `bootstrap_identity_client_id` in `environments/<env>.yml` as
`bootstrap_identity_client_id`. In delegated mode `trusted_repo` is the central
deploy repo; in self mode it is the app repo.

````

- [ ] **Step 2: Write the test** (`bootstrap/tests/root.tftest.hcl`)

```hcl
mock_provider "azurerm" {}

variables {
  subscription_id = "00000000-0000-0000-0000-000000000000"
  location        = "eastus2"
  environment     = "dev"
  trusted_repo    = "vgmello/deploy"
}

run "custom_role_is_exactly_the_four_capabilities" {
  command = plan

  assert {
    condition = length(setsubtract(
      azurerm_role_definition.bootstrap.permissions[0].actions,
      [
        "Microsoft.Resources/subscriptions/resourceGroups/read",
        "Microsoft.Resources/subscriptions/resourceGroups/write",
        "Microsoft.ManagedIdentity/userAssignedIdentities/read",
        "Microsoft.ManagedIdentity/userAssignedIdentities/write",
        "Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials/write",
        "Microsoft.Authorization/roleAssignments/read",
        "Microsoft.Authorization/roleAssignments/write",
      ]
    )) == 0
    error_message = "bootstrap role must contain only the approved actions"
  }

  assert {
    condition     = !contains(azurerm_role_definition.bootstrap.permissions[0].actions, "*")
    error_message = "bootstrap role must not contain a wildcard action"
  }

  assert {
    condition     = azurerm_federated_identity_credential.bootstrap.subject == "repo:vgmello/deploy:environment:dev"
    error_message = "bootstrap federation subject must trust the trusted repo environment"
  }
}
````

- [ ] **Step 3: Validate, format, test**

Run:

```bash
terraform -chdir=bootstrap init -backend=false -input=false
terraform -chdir=bootstrap fmt -check -recursive
terraform -chdir=bootstrap validate
terraform -chdir=bootstrap test
```

Expected: fmt clean, validate success, 1 test PASS. If fmt flags, run `terraform -chdir=bootstrap fmt -recursive` and re-check.

- [ ] **Step 4: Commit**

```bash
git add bootstrap
git commit -m "feat(terraform): manual per-subscription bootstrap stack (custom role + bootstrap identity)"
```

---

### Task 6: Per-tool bootstrap stack (RG + plan/apply MIs + roles + federated creds)

**Files:**

- Create: `terraform/bootstrap/versions.tf`, `variables.tf`, `main.tf`, `outputs.tf`
- Create: `terraform/bootstrap/tests/bootstrap.tftest.hcl`

**Interfaces:**

- Consumes: `federation_subjects` semantics from Task 2 (the subjects are passed in as a variable, computed by the CLI so the mapping lives in one place — Python).
- Produces: outputs `resource_group_name`, `plan_identity_client_id`, `apply_identity_client_id`.

- [ ] **Step 1: Write the module**

`terraform/bootstrap/versions.tf`:

```hcl
terraform {
  required_version = ">= 1.9.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}
```

`terraform/bootstrap/variables.tf`:

```hcl
variable "subscription_id" { type = string }
variable "location" { type = string }
variable "name" { type = string }
variable "environment" { type = string }

variable "plan_subjects" {
  description = "OIDC subjects the plan identity's federated credentials trust"
  type        = list(string)
}

variable "apply_subjects" {
  description = "OIDC subjects the apply identity's federated credentials trust"
  type        = list(string)
}
```

`terraform/bootstrap/main.tf`:

```hcl
provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
}

locals {
  rg = "rg-${var.name}-${var.environment}"
}

resource "azurerm_resource_group" "this" {
  name     = local.rg
  location = var.location
}

resource "azurerm_user_assigned_identity" "plan" {
  name                = "id-${var.name}-${var.environment}-plan"
  location            = var.location
  resource_group_name = azurerm_resource_group.this.name
}

resource "azurerm_user_assigned_identity" "apply" {
  name                = "id-${var.name}-${var.environment}-apply"
  location            = var.location
  resource_group_name = azurerm_resource_group.this.name
}

# plan identity: read-only across the RG, plus the data-plane reads plan refresh needs
resource "azurerm_role_assignment" "plan_reader" {
  scope                = azurerm_resource_group.this.id
  role_definition_name = "Reader"
  principal_id         = azurerm_user_assigned_identity.plan.principal_id
}

resource "azurerm_role_assignment" "plan_blob" {
  scope                = azurerm_resource_group.this.id
  role_definition_name = "Storage Blob Data Reader"
  principal_id         = azurerm_user_assigned_identity.plan.principal_id
}

resource "azurerm_role_assignment" "plan_kv" {
  scope                = azurerm_resource_group.this.id
  role_definition_name = "Key Vault Reader"
  principal_id         = azurerm_user_assigned_identity.plan.principal_id
}

# apply identity: write across the RG
resource "azurerm_role_assignment" "apply_contributor" {
  scope                = azurerm_resource_group.this.id
  role_definition_name = "Contributor"
  principal_id         = azurerm_user_assigned_identity.apply.principal_id
}

resource "azurerm_federated_identity_credential" "plan" {
  count               = length(var.plan_subjects)
  name                = "gha-plan-${count.index}"
  resource_group_name = azurerm_resource_group.this.name
  parent_id           = azurerm_user_assigned_identity.plan.id
  audience            = ["api://AzureADTokenExchange"]
  issuer              = "https://token.actions.githubusercontent.com"
  subject             = var.plan_subjects[count.index]
}

resource "azurerm_federated_identity_credential" "apply" {
  count               = length(var.apply_subjects)
  name                = "gha-apply-${count.index}"
  resource_group_name = azurerm_resource_group.this.name
  parent_id           = azurerm_user_assigned_identity.apply.id
  audience            = ["api://AzureADTokenExchange"]
  issuer              = "https://token.actions.githubusercontent.com"
  subject             = var.apply_subjects[count.index]
}
```

`terraform/bootstrap/outputs.tf`:

```hcl
output "resource_group_name" {
  value = azurerm_resource_group.this.name
}

output "plan_identity_client_id" {
  value = azurerm_user_assigned_identity.plan.client_id
}

output "apply_identity_client_id" {
  value = azurerm_user_assigned_identity.apply.client_id
}
```

- [ ] **Step 2: Write the test** (`terraform/bootstrap/tests/bootstrap.tftest.hcl`)

```hcl
mock_provider "azurerm" {}

variables {
  subscription_id = "00000000-0000-0000-0000-000000000000"
  location        = "eastus2"
  name            = "orders-api"
  environment     = "prod"
  plan_subjects   = ["repo:vgmello/deploy:environment:prod-plan"]
  apply_subjects  = ["repo:vgmello/deploy:environment:prod"]
}

run "identities_and_scoped_roles" {
  command = plan

  assert {
    condition     = azurerm_resource_group.this.name == "rg-orders-api-prod"
    error_message = "resource group name"
  }
  assert {
    condition     = azurerm_role_assignment.plan_reader.role_definition_name == "Reader"
    error_message = "plan identity must be Reader"
  }
  assert {
    condition     = azurerm_role_assignment.apply_contributor.role_definition_name == "Contributor"
    error_message = "apply identity must be Contributor"
  }
  assert {
    condition     = azurerm_role_assignment.plan_reader.scope == azurerm_resource_group.this.id && azurerm_role_assignment.apply_contributor.scope == azurerm_resource_group.this.id
    error_message = "both identities must be scoped to the resource group, not the subscription"
  }
  assert {
    condition     = azurerm_federated_identity_credential.apply[0].subject == "repo:vgmello/deploy:environment:prod"
    error_message = "apply federation subject passthrough"
  }
}
```

- [ ] **Step 3: Validate, format, test**

Run:

```bash
terraform -chdir=terraform/bootstrap init -backend=false -input=false
terraform -chdir=terraform/bootstrap fmt -check -recursive
terraform -chdir=terraform/bootstrap validate
terraform -chdir=terraform/bootstrap test
```

Expected: fmt clean, validate success, 1 test PASS.

- [ ] **Step 4: Commit**

```bash
git add terraform/bootstrap
git commit -m "feat(terraform): per-tool bootstrap stack (RG + plan/apply identities, RG-scoped roles, federated creds)"
```

---

### Task 7: CLI wiring — emit subjects and login plan for the workflow

**Files:**

- Modify: `cloudapp/cli.py`
- Modify: `tests/py/test_cli.py`

**Interfaces:**

- Consumes: `identity.federation_subjects`, `identity.login_plan`, `backend.backend_type`.
- Produces: CLI `login-plan` (prints JSON phases for an event + platform file) and `bootstrap-vars` (prints tfvars JSON for `terraform/bootstrap`: name, environment, subscription_id, location, plan_subjects, apply_subjects) given mode/app-repo/env.

- [ ] **Step 1: Write the failing tests** (append to `tests/py/test_cli.py`)

```python
def test_login_plan_command_emits_phases(capsys, monkeypatch):
    from conftest import ENVDIR
    rc = cli.main(["login-plan", "--event", "default_branch", "--platform-file", str(ENVDIR / "dev.yml")])
    assert rc == 0
    phases = json.loads(capsys.readouterr().out)
    assert [p["identity"] for p in phases] == ["bootstrap", "plan", "apply"]


def test_bootstrap_vars_command_delegated_uses_central_subjects(capsys):
    from conftest import ENVDIR
    rc = cli.main([
        "bootstrap-vars", "--name", "orders-api", "--environment", "prod",
        "--mode", "delegated", "--app-repo", "acme/orders",
        "--central-repo", "vgmello/deploy", "--platform-file", str(ENVDIR / "dev.yml"),
    ])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["plan_subjects"] == ["repo:vgmello/deploy:environment:prod-plan"]
    assert out["apply_subjects"] == ["repo:vgmello/deploy:environment:prod"]
    assert out["name"] == "orders-api"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/py/test_cli.py -q -k "login_plan or bootstrap_vars"`
Expected: FAIL (subcommands missing).

- [ ] **Step 3: Add the subcommands to `cloudapp/cli.py`**

Add imports at the top (`from . import backend, builds, dispatch, dockerbuild, gha, identity, manifest, resolve, runner, secrets, tfdeploy`) and these handlers + parsers:

```python
def cmd_login_plan(args):
    phases = identity.login_plan(args.event, backend.backend_type(args.platform_file))
    print(json.dumps(phases))


def cmd_bootstrap_vars(args):
    platform = _load_platform(args.platform_file)
    out = {
        "name": args.name,
        "environment": args.environment,
        "subscription_id": platform["subscription_id"],
        "location": platform["location"],
        "plan_subjects": identity.federation_subjects(
            "plan", args.mode, args.app_repo, args.central_repo, args.environment
        ),
        "apply_subjects": identity.federation_subjects(
            "apply", args.mode, args.app_repo, args.central_repo, args.environment
        ),
    }
    print(json.dumps(out))
```

Add a helper near `_load_json`:

```python
def _load_platform(path):
    from .yamlcompat import load_yaml
    return load_yaml(Path(path).read_text())
```

Register parsers in `main`:

```python
    p = sub.add_parser("login-plan")
    p.add_argument("--event", required=True)
    p.add_argument("--platform-file", required=True)
    p.set_defaults(func=cmd_login_plan)

    p = sub.add_parser("bootstrap-vars")
    p.add_argument("--name", required=True)
    p.add_argument("--environment", required=True)
    p.add_argument("--mode", required=True)
    p.add_argument("--app-repo", required=True)
    p.add_argument("--central-repo", required=True)
    p.add_argument("--platform-file", required=True)
    p.set_defaults(func=cmd_bootstrap_vars)
```

Extend the exception tuple in `main` to include `ValueError` from identity:

```python
    except (manifest.ManifestError, resolve.ResolveError, secrets.SyncError,
            tfdeploy.DeployError, backend.BackendError, dispatch.DispatchError, ValueError) as exc:
        gha.error(str(exc))
        return 1
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/py/test_cli.py -q`
Expected: PASS.

- [ ] **Step 5: Full suite + coverage**

Run: `python3 -m pytest tests/py -q --cov=cloudapp --cov-fail-under=90`
Expected: PASS, coverage ≥90%.

- [ ] **Step 6: Commit**

```bash
git add cloudapp/cli.py tests/py/test_cli.py
git commit -m "feat(cloudapp): login-plan and bootstrap-vars CLI commands"
```

---

### Task 8: Wire the deploy workflow + docs

**Files:**

- Modify: `.github/workflows/deploy.yml`
- Modify: `docs/usage.md`, `README.md`
- Create: `docs/trust-modes.md`

**Interfaces:**

- Consumes: CLI `login-plan`, `bootstrap-vars`; the two bootstrap stacks; `backend.render(stack=...)`.
- Produces: the runnable workflow. Note: end-to-end execution needs live OIDC + Azure/AWS and is deferred to sandbox integration; this task's automated gate is actionlint + the existing offline suites.

- [ ] **Step 1: Add the `mode` input and the delegated dispatch path**

In `.github/workflows/deploy.yml` `workflow_call.inputs`, add:

```yaml
mode:
  description: self (run here) or delegated (dispatch to the central deploy repo)
  type: string
  default: delegated
central_repo:
  description: central deploy repo for delegated mode
  type: string
  default: vgmello/deploy
```

- [ ] **Step 2: Replace each deploy job's single terraform-deploy with the phase loop**

For each `deploy-<i>` job, the deploy steps become: check out `.deploy`; `azure/login` per phase using the identity that phase names; run `terraform-deploy` with `--stack` and `--targets` from the phase; `sync-secrets` between the bootstrap phase and the plan phase (default-branch only). The bootstrap phase runs `terraform/bootstrap` with `bootstrap-vars` output as `-var-file`; plan/apply phases run the main `terraform/` stack under the plan/apply identities. Use `python3 -m cloudapp login-plan --event "${{ github.event_name == 'pull_request' && 'pull_request' || 'default_branch' }}" --platform-file <file>` to drive a matrix or sequential steps.

Because this is a large structural change to a generated file, regenerate `deploy.yml` from the Python generator pattern already used (extend the generator script if present) OR hand-edit all four indexed jobs identically. Keep every `${{ }}`-into-bash value routed through `env:` (established rule).

- [ ] **Step 3: terraform-deploy action learns `--stack`**

Modify `.github/actions/terraform-deploy/action.yml` and `cloudapp/tfdeploy.py`/`cli.py` so `terraform-deploy` accepts `--stack main|bootstrap` and `--terraform-dir` can point at `terraform/bootstrap`; `prepare`/`deploy` pass `stack` through to `backend.render(..., stack=stack)`. Add a `test_tfdeploy` case asserting the bootstrap stack key flows into the backend lines.

- [ ] **Step 4: Write `docs/trust-modes.md`** covering: the three identities and their scopes; self vs delegated (with the federation-subject table from the spec); the one-time `bootstrap/` setup; the two state files; the S3 backend's two-login flow; and the live-only gaps. Link it from `README.md` and `docs/usage.md`.

- [ ] **Step 5: Verify offline gates**

Run:

```bash
actionlint
python3 -m pytest tests/py -q --cov=cloudapp --cov-fail-under=90
terraform -chdir=terraform test && terraform -chdir=terraform/bootstrap test && terraform -chdir=bootstrap test
terraform -chdir=terraform fmt -check -recursive
```

Expected: all clean.

- [ ] **Step 6: Commit**

```bash
git add .github docs README.md cloudapp tests
git commit -m "feat: wire trust modes and identity handoff into the deploy workflow; trust-modes docs"
```

---

## Self-Review Notes

- Spec coverage: identity model (Tasks 5, 6), state backends azurerm+s3 (Task 1), federation subjects (Task 2), login sequencing (Task 3), delegated dispatch (Task 4), CLI glue (Task 7), workflow + docs (Task 8). The manual bootstrap subject and the "two state files" are Tasks 5 and 1 respectively.
- The federation-subject mapping lives ONCE, in Python (`identity.federation_subjects`), and is passed into the per-tool Terraform bootstrap as `plan_subjects`/`apply_subjects` variables — Terraform never re-derives it.
- Live-only, explicitly deferred (documented in Task 8): real OIDC token exchange (Azure + AWS), RBAC propagation timing after the per-tool bootstrap creates the plan/apply identities, cross-cloud two-login runs, and the end-to-end `deploy.yml` execution. These match the platform's existing sandbox-integration deferral.
- Task 8 is integration-heavy and its automated gate is actionlint + the offline suites; its correctness ultimately needs the sandbox run. Reviewers should treat Task 8 as scaffolding to be validated live, not as offline-proven behavior.
