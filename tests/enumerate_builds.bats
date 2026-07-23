#!/usr/bin/env bats

setup() {
  REPO_ROOT="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"
  PARSE="$REPO_ROOT/.github/actions/parse-manifest/parse-manifest.sh"
  SCRIPT="$REPO_ROOT/.github/actions/docker-build/enumerate-builds.sh"
  FIXTURES="$REPO_ROOT/tests/fixtures/manifests"
  GOLDEN="$REPO_ROOT/tests/golden"
  TMP="$(mktemp -d)"
}

teardown() { rm -rf "$TMP"; }

check() { # manifest env name
  "$PARSE" "$FIXTURES/$1.yml" "$TMP/$1" > /dev/null
  run "$SCRIPT" "$TMP/$1/tool.$2.json" "$3" acr.example.io shaabc
  [ "$status" -eq 0 ]
  diff <(echo "$output" | jq -S .) <(jq -S . "$GOLDEN/builds.$1.json")
}

@test "minimal: default build for shorthand app" {
  check minimal dev orders-api
}

@test "full: identical (file,context) dedupes into one build across apps and functions" {
  check full prod orders-api
}

@test "multi: prebuilt-image containers are excluded from builds" {
  check multi dev billing
}

@test "partial: prebuilt-image function excluded, app default-built" {
  check partial dev partial
}
