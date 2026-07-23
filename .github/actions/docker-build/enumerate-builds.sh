#!/usr/bin/env bash
set -euo pipefail

# usage: enumerate-builds.sh <tool-json> <tool-name> <registry> <git-sha>
# Emits {"builds": [{"file", "context", "keys": [...]}], "tags": {"<key>": "<image-ref>"}}
# Keys: "<app_key>/<container_key>" for apps, "<function_key>" for functions.
# Entries with image: are skipped; entries without docker: default to ./Dockerfile + . ;
# identical (file, context) pairs share one build.
TOOL="${1:?tool json required}"
NAME="${2:?tool name required}"
REGISTRY="${3:?registry required}"
SHA="${4:?git sha required}"

jq --arg name "$NAME" --arg registry "$REGISTRY" --arg sha "$SHA" '
  def entries:
    [ (.apps // {} | to_entries[] | .key as $a
       | .value.containers | to_entries[]
       | select(.value.image == null)
       | { key: "\($a)/\(.key)",
           file: (.value.docker.file // "./Dockerfile"),
           context: (.value.docker.context // ".") }),
      (.functions // {} | to_entries[]
       | select(.value.image == null)
       | { key: .key,
           file: (.value.docker.file // "./Dockerfile"),
           context: (.value.docker.context // ".") }) ];

  entries as $e
  | { builds: ($e | group_by([.file, .context])
               | map({ file: .[0].file, context: .[0].context, keys: (map(.key) | sort) })),
      tags: ($e | map({ (.key): "\($registry)/\($name)/\(.key | gsub("/"; "-")):\($sha)" }) | add // {}) }
' "$TOOL"
