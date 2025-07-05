#!/bin/bash

set -u

BLUE='\033[1;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

print_status() {
    echo -e "${GREEN}==> $1${NC}"
}
print_info() {
    echo -e "${BLUE}$1${NC}"
}
print_warn() {
    echo -e "${YELLOW}Warning:${NC} $1"
}
print_error() {
    echo -e "${RED}Error:${NC} $1"
}

# 1. Set up venv
if [ ! -d "image-webui/venv" ]; then
    print_status "Creating Python virtual environment in image-webui/venv..."
    python3 -m venv image-webui/venv || { print_error "Failed to create venv"; exit 1; }
else
    print_info "Python venv already exists. Skipping creation."
fi

# 2. Install dependencies
print_status "Installing Python dependencies from image-webui/requirements.txt..."
image-webui/venv/bin/pip install --upgrade pip
image-webui/venv/bin/pip install -r image-webui/requirements.txt || { print_error "Failed to install Python dependencies"; exit 1; }

# 2.5. Verify critical dependencies
print_status "Verifying critical dependencies..."
image-webui/venv/bin/python -c "import pillow_heif; print('✅ pillow-heif: OK')" || print_warn "pillow-heif not available - HEIC files may not work properly"
image-webui/venv/bin/python -c "import PIL; print('✅ Pillow: OK')" || print_error "Pillow not available"
image-webui/venv/bin/python -c "import requests; print('✅ requests: OK')" || print_error "requests not available"
image-webui/venv/bin/python -c "import yaml; print('✅ PyYAML: OK')" || print_error "PyYAML not available"

# 3. Create CLI wrapper scripts that activate the virtual environment
BIN_DIR="/usr/local/bin"
CLI_WRAPPER="$BIN_DIR/image-tagger"
SEARCH_WRAPPER="$BIN_DIR/image-search"
PROJECT_ROOT="$(pwd)"

if [ "$(id -u)" -eq 0 ]; then
    print_status "Creating CLI wrapper scripts in $BIN_DIR..."
    
    # Remove any existing symlinks or files
    rm -f "$CLI_WRAPPER" "$SEARCH_WRAPPER"
    
    # Create image-tagger wrapper (use the new backend CLI)
    cat > "$CLI_WRAPPER" << EOF
#!/bin/bash
# Wrapper script for image-tagger CLI (using new backend)
cd "$PROJECT_ROOT"
source image-webui/venv/bin/activate
exec python image-webui/backend/image_tagger_cli.py "\$@"
EOF
    
    # Create image-search wrapper
    cat > "$SEARCH_WRAPPER" << EOF
#!/bin/bash
# Wrapper script for image-search CLI
cd "$PROJECT_ROOT"
source image-webui/venv/bin/activate
exec python image-webui/backend/image-search.py "\$@"
EOF
    
    chmod +x "$CLI_WRAPPER"
    chmod +x "$SEARCH_WRAPPER"
    
    print_info "CLI wrapper scripts created:"
    echo "  $CLI_WRAPPER"
    echo "  $SEARCH_WRAPPER"
else
    print_warn "Not running as root. Skipping CLI wrapper creation in $BIN_DIR."
    print_info "To create CLI wrappers system-wide, run:"
    echo "  sudo $0"
fi

print_status "Installation complete!"
echo
print_info "To activate the Python environment:"
echo "  source image-webui/venv/bin/activate"
echo
print_info "To launch the Web UI:"
echo "  cd image-webui && ./run.sh"
echo
print_info "To use the CLI:"
echo "  image-tagger [options] <path>"
echo
print_info "To use the search tool:"
echo "  image-search [options] <query>"
echo
print_status "Done. Enjoy!" 