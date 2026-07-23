#!/usr/bin/env bash
set -euo pipefail

# usage: render-backend-config.sh <platform-env-yml> <tool-name> <env-name>
# Prints -backend-config key=value lines (one per line).
PLATFORM="${1:?platform env yml required}"
NAME="${2:?tool name required}"
ENV_NAME="${3:?environment required}"

RG="$(yq '.terraform_state.resource_group' "$PLATFORM")"
ACCOUNT="$(yq '.terraform_state.storage_account' "$PLATFORM")"
CONTAINER="$(yq '.terraform_state.container' "$PLATFORM")"

declare -A KEYS=([RG]=resource_group [ACCOUNT]=storage_account [CONTAINER]=container)
for v in RG ACCOUNT CONTAINER; do
  if [ -z "${!v}" ] || [ "${!v}" = "null" ]; then
    echo "error: terraform_state.${KEYS[$v]} missing in $PLATFORM" >&2
    exit 1
  fi
done

cat <<CONFIG
resource_group_name=$RG
storage_account_name=$ACCOUNT
container_name=$CONTAINER
key=$NAME/$ENV_NAME.tfstate
use_oidc=true
use_azuread_auth=true
CONFIG
