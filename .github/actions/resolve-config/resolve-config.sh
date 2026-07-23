#!/usr/bin/env bash
set -euo pipefail

# usage: resolve-config.sh <tool-json> <platform-env-yml> <env-name> <out-file>
TOOL="${1:?tool json required}"
PLATFORM_FILE="${2:?platform env yml required}"
ENV_NAME="${3:?environment name required}"
OUT_FILE="${4:?output file required}"

if [ ! -f "$PLATFORM_FILE" ]; then
  echo "error: platform config not found: $PLATFORM_FILE (environment '$ENV_NAME' has no platform config file)" >&2
  exit 1
fi

PLATFORM_JSON="$(yq -o=json '.' "$PLATFORM_FILE")"
jq --argjson platform "$PLATFORM_JSON" --arg env "$ENV_NAME" \
  '{config: (. + {environment: $env, platform: $platform})}' \
  "$TOOL" > "$OUT_FILE"
