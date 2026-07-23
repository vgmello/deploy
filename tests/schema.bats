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

@test "empty environments map is invalid" {
  run validate invalid-empty-environments.yml
  [ "$status" -ne 0 ]
}
