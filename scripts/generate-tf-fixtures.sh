#!/usr/bin/env bash
set -euo pipefail

# Regenerates terraform test fixtures by running real manifests through the
# parse-manifest -> resolve-config pipeline. CI diffs the result to keep
# committed fixtures honest.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PARSE="$ROOT/.github/actions/parse-manifest/parse-manifest.sh"
RESOLVE="$ROOT/.github/actions/resolve-config/resolve-config.sh"
PLATFORM="$ROOT/tests/fixtures/environments/dev.yml"
OUTDIR="$ROOT/terraform/tests/fixtures"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

mkdir -p "$OUTDIR"

gen() {
  local name="$1" env="$2"
  "$PARSE" "$ROOT/tests/fixtures/manifests/$name.yml" "$TMP/$name" > /dev/null
  "$RESOLVE" "$TMP/$name/tool.$env.json" "$PLATFORM" "$env" "$OUTDIR/tfvars.$name.$env.json"
  echo "wrote terraform/tests/fixtures/tfvars.$name.$env.json"
}

gen minimal dev
gen full prod
gen multi dev
gen partial dev
