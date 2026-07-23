#!/usr/bin/env bats

setup() {
  REPO_ROOT="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"
  PARSE="$REPO_ROOT/.github/actions/parse-manifest/parse-manifest.sh"
  RESOLVE="$REPO_ROOT/.github/actions/resolve-config/resolve-config.sh"
  FIXTURES="$REPO_ROOT/tests/fixtures/manifests"
  GOLDEN="$REPO_ROOT/tests/golden"
  ENVDIR="$REPO_ROOT/tests/fixtures/environments"
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
