#!/bin/bash
set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${BLUE}$1${NC}"
}

print_success() {
    echo -e "${GREEN}$1${NC}"
}

print_warning() {
    echo -e "${YELLOW}$1${NC}"
}

print_error() {
    echo -e "${RED}$1${NC}"
}

# Check if gomplate is available
check_gomplate() {
    if ! command -v gomplate &> /dev/null; then
        print_error "gomplate is not installed. Please install gomplate:"
        echo "  - macOS: brew install gomplate"
        echo "  - Linux: https://github.com/hairyhenderson/gomplate/releases"
        exit 1
    fi
    print_success "gomplate is available"
}

# Render a single template file with gomplate
render_template() {
    local template_file="$1"
    local output_file="$2"
    
    if [[ ! -f "$template_file" ]]; then
        print_warning "Template file not found: $template_file"
        return 1
    fi
    
    print_info "Rendering $(basename "$output_file") from template…"
    gomplate -f "$template_file" -o "$output_file"
    
    print_success "Generated: $output_file"
}

# Copy all non-template files
copy_static_files() {
    local config_dir="$1"
    local output_dir="$2"
    
    print_info "Copying static files from $config_dir..."
    
    find "$config_dir" -type f ! -name '*.template.*' | while read -r file; do
        rel_path="${file#$config_dir/}"
        out_file="$output_dir/$rel_path"
        
        mkdir -p "$(dirname "$out_file")"
        cp "$file" "$out_file"
        print_success "Copied: $rel_path"
    done
}

# Create directory if it doesn't exist
ensure_directory() {
    local dir="$1"
    if [[ ! -d "$dir" ]]; then
        print_info "Creating directory: $dir"
        mkdir -p "$dir"
    fi
}



# Load environment variables from credentials.env
load_environment() {
    local credentials_file="$1"
    
    if [[ -f "$credentials_file" ]]; then
        print_info "Loading environment variables from credentials.env..."
        while IFS='=' read -r key value; do
            if [[ ! "$key" =~ ^# ]] && [[ -n "$key" ]]; then
                export "$key=$value"
            fi
        done < "$credentials_file"
        print_success "Environment variables loaded"
    else
        print_warning "credentials.env not found, using default values"
    fi
}

# Process all template files
process_templates() {
    local config_dir="$1"
    local generated_dir="$2"
    
    print_info "Processing template files..."
    find "$config_dir" -type f -name '*.template.*' | while read -r template_file; do
        rel_path="${template_file#$config_dir/}"
        # Remove .template. from the filename
        output_path=$(echo "$rel_path" | sed -E 's/\.template\.([^.]+)$/.\1/')
        output_file="$generated_dir/$output_path"
        
        mkdir -p "$(dirname "$output_file")"
        render_template "$template_file" "$output_file"
    done
}


main() {
    print_info "Starting configuration rendering..."
    
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
    CONFIG_DIR="$PROJECT_ROOT/config"
    GENERATED_DIR="$PROJECT_ROOT/generated-config"
    
    check_gomplate
    load_environment "$PROJECT_ROOT/credentials.env"
    
    print_info "Project root: $PROJECT_ROOT"
    print_info "Config directory: $CONFIG_DIR"
    print_info "Generated directory: $GENERATED_DIR"
    
    rm -rf "$GENERATED_DIR"/*
    ensure_directory "$GENERATED_DIR"
    copy_static_files "$CONFIG_DIR" "$GENERATED_DIR"
    process_templates "$CONFIG_DIR" "$GENERATED_DIR"
    
    print_success "Configuration rendering completed!"
    print_info "Generated files are in: $GENERATED_DIR"
}

# Run main function
main "$@"
