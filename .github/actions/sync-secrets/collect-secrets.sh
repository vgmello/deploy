#!/usr/bin/env bash
set -euo pipefail

# usage: collect-secrets.sh <tool-json>
# Emits [{"name": "STRIPE_KEY", "kv_name": "stripe-key"}, ...] for every secret
# referenced by any container or function in the manifest.
TOOL="${1:?tool json required}"

jq '
  [ (.apps // {} | .[] | .containers // {} | .[] | .secrets // [] | .[]),
    (.functions // {} | .[] | .secrets // [] | .[]) ]
  | unique
  | map({ name: ., kv_name: (ascii_downcase | gsub("_"; "-")) })
' "$TOOL"
