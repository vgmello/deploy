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
