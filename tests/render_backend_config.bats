#!/usr/bin/env bats

setup() {
  REPO_ROOT="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"
  SCRIPT="$REPO_ROOT/.github/actions/terraform-deploy/render-backend-config.sh"
  ENVDIR="$REPO_ROOT/tests/fixtures/environments"
  TMP="$(mktemp -d)"
}

teardown() { rm -rf "$TMP"; }

@test "renders backend config from platform yml with per-tool state key" {
  run "$SCRIPT" "$ENVDIR/dev.yml" orders-api dev
  [ "$status" -eq 0 ]
  [ "${lines[0]}" = "resource_group_name=rg-tfstate" ]
  [ "${lines[1]}" = "storage_account_name=sttfstatedev" ]
  [ "${lines[2]}" = "container_name=tfstate" ]
  [ "${lines[3]}" = "key=orders-api/dev.tfstate" ]
  [ "${lines[4]}" = "use_oidc=true" ]
  [ "${lines[5]}" = "use_azuread_auth=true" ]
}

@test "fails on platform yml without terraform_state" {
  printf 'location: eastus2\n' > "$TMP/bad.yml"
  run "$SCRIPT" "$TMP/bad.yml" orders-api dev
  [ "$status" -ne 0 ]
  [[ "$output" == *"terraform_state"* ]]
}
