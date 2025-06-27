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

# 3. Symlink CLI and search tools
BIN_DIR="/usr/local/bin"
CLI_SRC="image-webui/backend/image_tagger_cli.py"
SEARCH_SRC="image-webui/backend/image-search.py"
CLI_LINK="$BIN_DIR/image-tagger"
SEARCH_LINK="$BIN_DIR/image-search"

if [ "$(id -u)" -eq 0 ]; then
    print_status "Creating symlinks in $BIN_DIR..."
    ln -sf "$(pwd)/$CLI_SRC" "$CLI_LINK"
    chmod +x "$CLI_SRC"
    ln -sf "$(pwd)/$SEARCH_SRC" "$SEARCH_LINK"
    chmod +x "$SEARCH_SRC"
    print_info "Symlinks created:"
    echo "  $CLI_LINK -> $CLI_SRC"
    echo "  $SEARCH_LINK -> $SEARCH_SRC"
else
    print_warn "Not running as root. Skipping symlink creation in $BIN_DIR."
    print_info "To use the CLI and search tools system-wide, run:"
    echo "  sudo ln -sf \"$(pwd)/$CLI_SRC\" $CLI_LINK"
    echo "  sudo chmod +x $CLI_SRC"
    echo "  sudo ln -sf \"$(pwd)/$SEARCH_SRC\" $SEARCH_LINK"
    echo "  sudo chmod +x $SEARCH_SRC"
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