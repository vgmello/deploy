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
rm -f "$OUT"/tool.*.json "$OUT"/outputs.txt

yq -o=json '.' "$MANIFEST" > "$OUT/manifest.json"
npx --yes ajv-cli@5 validate --spec=draft2020 -s "$SCHEMA" -d "$OUT/manifest.json"

NAME="$(yq '.name' "$MANIFEST")"
ENVS="$(yq -o=json -I=0 '(.environments // {"dev": {}}) | keys' "$MANIFEST")"

DOCKER=false
DOCKER_ENTRIES="$(yq '[(.apps // {})[], (.functions // {})[]] | map(select(.docker != null)) | length' "$MANIFEST")"
if [ "$DOCKER_ENTRIES" != "0" ] || [ -f "$APP_ROOT/Dockerfile" ]; then
  DOCKER=true
fi

yq 'del(.environments)' "$MANIFEST" > "$OUT/base.yml"

for env in $(echo "$ENVS" | yq -p=json '.[]'); do
  yq ".environments.\"$env\" // {}" "$MANIFEST" > "$OUT/overlay.$env.yml"
  yq eval-all '. as $item ireduce ({}; . * $item)' \
    "$OUT/base.yml" "$OUT/overlay.$env.yml" > "$OUT/merged.$env.yml"

  # fill per-entry defaults for each compute section present
  for pair in apps:app functions:function static_sites:static_site; do
    section="${pair%%:*}"
    deffile="${pair##*:}"
    if [ "$(yq ".$section" "$OUT/merged.$env.yml")" != "null" ]; then
      yq -i ".$section |= map_values(load(\"$DEFAULTS/$deffile.yml\") * .)" "$OUT/merged.$env.yml"
    fi
  done

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

OUTPUTS="name=$NAME
environments=$ENVS
docker=$DOCKER"

echo "$OUTPUTS" > "$OUT/outputs.txt"
if [ -n "${GITHUB_OUTPUT:-}" ]; then
  echo "$OUTPUTS" >> "$GITHUB_OUTPUT"
fi
