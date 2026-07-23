#!/usr/bin/env bats

setup() {
  REPO_ROOT="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"
  PARSE="$REPO_ROOT/.github/actions/parse-manifest/parse-manifest.sh"
  SCRIPT="$REPO_ROOT/.github/actions/sync-secrets/collect-secrets.sh"
  FIXTURES="$REPO_ROOT/tests/fixtures/manifests"
  TMP="$(mktemp -d)"
}

teardown() { rm -rf "$TMP"; }

@test "full manifest yields STRIPE_KEY mapped to stripe-key" {
  "$PARSE" "$FIXTURES/full.yml" "$TMP/full" > /dev/null
  run "$SCRIPT" "$TMP/full/tool.dev.json"
  [ "$status" -eq 0 ]
  [ "$(echo "$output" | jq -c .)" = '[{"name":"STRIPE_KEY","kv_name":"stripe-key"}]' ]
}

@test "manifest without secrets yields empty list" {
  "$PARSE" "$FIXTURES/minimal.yml" "$TMP/min" > /dev/null
  run "$SCRIPT" "$TMP/min/tool.dev.json"
  [ "$status" -eq 0 ]
  [ "$(echo "$output" | jq -c .)" = "[]" ]
}
