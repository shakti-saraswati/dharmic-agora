#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "Usage: $0 <node-slug> <node-name> <domain>"
  exit 1
fi

slug="$1"
name="$2"
domain="$3"

if [[ "$slug" =~ ^anchor-([0-9]{1,2})- ]]; then
  idx="${BASH_REMATCH[1]}"
  node_coordinate="$(printf "Node_%02d" "$((10#$idx))")"
else
  echo "Could not derive node_coordinate from slug: $slug"
  echo "Expected format: anchor-<nn>-<name>"
  exit 1
fi

root="nodes/anchors/${slug}"
if [[ -e "$root" ]]; then
  echo "Node already exists: $root"
  exit 1
fi

mkdir -p "$root"
cp -R nodes/template/* "$root/"

sed -i '' "s|node_id: \"template\"|node_id: \"${slug}\"|" "$root/node.yaml"
sed -i '' "s|node_coordinate: \"Node_00\"|node_coordinate: \"${node_coordinate}\"|" "$root/node.yaml"
sed -i '' "s|name: \"Template Node\"|name: \"${name}\"|" "$root/node.yaml"
sed -i '' "s|domain: \"replace\"|domain: \"${domain}\"|" "$root/node.yaml"

printf "Initialized node: %s\n" "$root"
