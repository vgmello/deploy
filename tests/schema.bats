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

@test "legacy type key is invalid" {
  run validate invalid-legacy-type.yml
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

@test "manifest without apps, functions, or static_sites is invalid" {
  run validate invalid-no-compute.yml
  [ "$status" -ne 0 ]
}

@test "multi-container manifest with ingress object is valid" {
  run validate multi.yml
  [ "$status" -eq 0 ]
}

@test "app mixing containers map with shorthand container fields is invalid" {
  run validate invalid-mixed-container.yml
  [ "$status" -ne 0 ]
}

@test "database type sqlserver is valid" {
  run validate multi.yml
  [ "$status" -eq 0 ]
}

@test "unknown database type is invalid" {
  run validate invalid-db-type.yml
  [ "$status" -ne 0 ]
}

@test "singular app shorthand is valid" {
  run validate minimal.yml
  [ "$status" -eq 0 ]
}

@test "app and apps together is invalid" {
  run validate invalid-app-and-apps.yml
  [ "$status" -ne 0 ]
}

@test "container with prebuilt image is valid" {
  run validate multi.yml
  [ "$status" -eq 0 ]
}

@test "image and docker together is invalid" {
  run validate invalid-image-and-docker.yml
  [ "$status" -ne 0 ]
}

@test "partial manifest (shorthand, partial ingress/replicas, static site, function image) is valid" {
  run validate partial.yml
  [ "$status" -eq 0 ]
}

@test "function with image and docker together is invalid" {
  run validate invalid-function-image-docker.yml
  [ "$status" -ne 0 ]
}

@test "non-string env value is invalid" {
  run validate invalid-env-number.yml
  [ "$status" -ne 0 ]
}
