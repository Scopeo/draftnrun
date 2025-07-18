#!/bin/bash
set -euo pipefail

# Function to process template files with envsubst
process_template() {
    local template_file="$1"
    local output_file="$2"
    
    if [[ ! -f "$template_file" ]]; then
        echo "⚠️  Template file not found: $template_file"
        return 1
    fi
    
    echo "🔧 Rendering $(basename "$output_file") from template…"
    envsubst < "$template_file" > "$output_file"
    
    # Remove template file to avoid collisions
    rm "$template_file"
    
    echo "✅ Final $(basename "$output_file"):"
    cat "$output_file"
    echo ""
}

echo "🔧 Validating environment variables…"
: "${GRAFANA_PROMETHEUS_HOST:?GRAFANA_PROMETHEUS_HOST is not set}"
: "${GRAFANA_PROMETHEUS_PORT:?GRAFANA_PROMETHEUS_PORT is not set}"
: "${GRAFANA_TEMPO_HOST:?GRAFANA_TEMPO_HOST is not set}"
: "${GRAFANA_TEMPO_PORT:?GRAFANA_TEMPO_PORT is not set}"

# Process all template files
process_template "/etc/grafana/provisioning/datasources/datasources.template.yaml" \
                "/etc/grafana/provisioning/datasources/datasources.yaml"

echo "🚀 Starting Grafana…"
/run.sh
