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
