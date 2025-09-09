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



# Parse command line arguments
parse_arguments() {
    CONFIG_DIR=""
    OUTPUT_DIR=""
    ENV_FILE=""
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --config-dir)
                CONFIG_DIR="$2"
                shift 2
                ;;
            --output-dir)
                OUTPUT_DIR="$2"
                shift 2
                ;;
            --env-file)
                ENV_FILE="$2"
                shift 2
                ;;
            -h|--help)
                echo "Usage: $0 [OPTIONS]"
                echo ""
                echo "Options:"
                echo "  --config-dir DIR     Directory with templates (default: PROJECT_ROOT/config)"
                echo "  --output-dir DIR     Output directory (default: PROJECT_ROOT/generated-config)"
                echo "  --env-file FILE      Environment file to load (default: PROJECT_ROOT/credentials.env)"
                echo "  -h, --help          Show this help message"
                echo ""
                echo "Examples:"
                echo "  $0                                    # Use defaults"
                echo "  $0 --output-dir custom-output/        # Custom output only"
                echo "  $0 --config-dir ../config --output-dir ./output --env-file .env"
                exit 0
                ;;
            *)
                print_error "Unknown option: $1"
                echo "Use -h or --help for usage information"
                exit 1
                ;;
        esac
    done
}

# Load environment variables from credentials.env
load_environment() {
    local credentials_file="$1"
    
    if [[ -f "$credentials_file" ]]; then
        print_info "Loading environment variables from $credentials_file..."
        while IFS='=' read -r key value; do
            if [[ ! "$key" =~ ^# ]] && [[ -n "$key" ]]; then
                export "$key=$value"
            fi
        done < "$credentials_file"
        print_success "Environment variables loaded"
    else
        print_warning "$credentials_file not found, using default values"
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
    
    # Parse command line arguments
    parse_arguments "$@"
    
    # Set defaults if not provided
    CONFIG_DIR="${CONFIG_DIR:-$PROJECT_ROOT/config}"
    OUTPUT_DIR="${OUTPUT_DIR:-$PROJECT_ROOT/generated-config}"
    ENV_FILE="${ENV_FILE:-$PROJECT_ROOT/credentials.env}"
    
    check_gomplate
    load_environment "$ENV_FILE"
    
    print_info "Project root: $PROJECT_ROOT"
    print_info "Config directory: $CONFIG_DIR"
    print_info "Output directory: $OUTPUT_DIR"
    print_info "Environment file: $ENV_FILE"
    
    rm -rf "$OUTPUT_DIR"/*
    ensure_directory "$OUTPUT_DIR"
    copy_static_files "$CONFIG_DIR" "$OUTPUT_DIR"
    process_templates "$CONFIG_DIR" "$OUTPUT_DIR"
    
    print_success "Configuration rendering completed!"
    print_info "Generated files are in: $OUTPUT_DIR"
}

# Run main function
main "$@"
