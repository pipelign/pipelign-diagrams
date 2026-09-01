#!/usr/bin/env sh
set -eu

image_name="${1:-pipelign-diagrams:local}"
output_path="${2:-build/pipelign-diagrams.spdx.json}"

mkdir -p "$(dirname "$output_path")"

docker sbom "$image_name" \
    --format spdx-json \
    --output "$output_path"

echo "Wrote SPDX JSON SBOM to $output_path"
